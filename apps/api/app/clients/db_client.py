"""Async SQLAlchemy engines and session factories over psycopg 3.

Two engines, one per database role:

- the application engine runs as `ontaix_app`. Row-level security confines that role to the
  organization named by the transaction setting `ontaix.tenant_id`; every transaction of an
  application session sets it from `session.info["tenant_id"]` as it begins, and sets it empty
  when the session names no organization, which matches no row (fail closed).
- the platform engine runs as `ontaix_platform`: sign-in, the platform portal and the jobs that
  work across organizations.

Each connection switches to its role with `SET ROLE` as it opens, so the login it connects with
must be a member of that role; a login that is not fails to connect instead of running with its
own privileges. Routers receive a session through `session_dependency` and pass it down to
services; repositories are the only code that runs statements on it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

ASYNC_DRIVER_PREFIX = "postgresql+psycopg://"
APP_ROLE = "ontaix_app"
PLATFORM_ROLE = "ontaix_platform"
TENANT_KEY = "tenant_id"
_SET_TENANT = text("SELECT set_config('ontaix.tenant_id', :tenant, true)")

_engine: AsyncEngine | None = None
_platform_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_platform_session_factory: async_sessionmaker[AsyncSession] | None = None


class TenantScopedSession(Session):
    """The synchronous session behind every application `AsyncSession`."""


@event.listens_for(TenantScopedSession, "after_begin")
def _set_tenant_on_begin(session: Session, _transaction: Any, connection: Any) -> None:
    """Name the session's organization for the new transaction, or none (no row visible)."""
    tenant_id = session.info.get(TENANT_KEY)
    connection.execute(_SET_TENANT, {"tenant": str(tenant_id) if tenant_id else ""})


def async_database_url(url: str) -> str:
    """Rewrite a plain `postgresql://` URL to the psycopg 3 SQLAlchemy driver form."""
    if url.startswith(ASYNC_DRIVER_PREFIX):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return ASYNC_DRIVER_PREFIX + url[len(prefix) :]
    return url


def configure_engine(url: str, platform_url: str | None = None) -> AsyncEngine:
    """Build the process-wide engines for `url` (application role) and `platform_url` (platform
    role, default `url`), replacing any earlier ones."""
    global _engine, _platform_engine, _session_factory, _platform_session_factory
    _engine = _role_engine(url, APP_ROLE)
    _platform_engine = _role_engine(platform_url or url, PLATFORM_ROLE)
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, sync_session_class=TenantScopedSession
    )
    _platform_session_factory = async_sessionmaker(_platform_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Return the application engine, building both from the settings on first use."""
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("ONTAIX_DATABASE_URL is not set")
        configure_engine(settings.database_url, settings.platform_database_url_or_default())
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the application session factory. Its sessions see no organization's rows until
    one is named with `bind_tenant`; use `tenant_session` to open one already bound."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


def get_platform_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the platform session factory, for sign-in, the platform portal and
    cross-organization jobs only."""
    get_engine()
    assert _platform_session_factory is not None
    return _platform_session_factory


def tenant_session(tenant_id: uuid.UUID) -> AsyncSession:
    """A new application session bound to one organization."""
    return get_session_factory()(info={TENANT_KEY: tenant_id})


def platform_session() -> AsyncSession:
    """A new platform session."""
    return get_platform_session_factory()()


async def bind_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Name the organization of an application session: its open transaction at once, and
    every transaction it begins later."""
    session.info[TENANT_KEY] = tenant_id
    if session.in_transaction():
        await session.execute(_SET_TENANT, {"tenant": str(tenant_id)})


async def dispose_engine() -> None:
    """Close every pooled connection; used at shutdown and between test databases."""
    global _engine, _platform_engine, _session_factory, _platform_session_factory
    for engine in (_engine, _platform_engine):
        if engine is not None:
            await engine.dispose()
    _engine = _platform_engine = None
    _session_factory = _platform_session_factory = None


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one application session per request.

    The session commits when the handler returns normally and rolls back on any exception,
    so every state change of a request lands in one transaction. It sees no organization's rows
    until the caller dependency binds the caller's organization.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def platform_session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one platform session per request, for `/auth` and `/admin`."""
    async with get_platform_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def _role_engine(url: str, role: str) -> AsyncEngine:
    engine = create_async_engine(
        async_database_url(url),
        pool_pre_ping=True,
        # Statement errors never carry bound values (labels, emails) into logs or responses.
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _switch_role(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET ROLE {role}")
        cursor.close()
        dbapi_connection.commit()

    return engine
