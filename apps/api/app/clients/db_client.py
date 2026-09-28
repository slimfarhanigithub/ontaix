"""Async SQLAlchemy engine and session factory over psycopg 3.

Routers receive a session through `session_dependency` and pass it down to services;
repositories are the only code that runs statements on it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

ASYNC_DRIVER_PREFIX = "postgresql+psycopg://"

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def async_database_url(url: str) -> str:
    """Rewrite a plain `postgresql://` URL to the psycopg 3 SQLAlchemy driver form."""
    if url.startswith(ASYNC_DRIVER_PREFIX):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return ASYNC_DRIVER_PREFIX + url[len(prefix) :]
    return url


def configure_engine(url: str) -> AsyncEngine:
    """Build the process-wide engine for `url`, replacing any earlier one."""
    global _engine, _session_factory
    _engine = create_async_engine(
        async_database_url(url),
        pool_pre_ping=True,
        # Statement errors never carry bound values (labels, emails) into logs or responses.
        hide_parameters=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Return the engine, building it from ONTAIX_DATABASE_URL on first use."""
    if _engine is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("ONTAIX_DATABASE_URL is not set")
        configure_engine(url)
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the process-wide engine."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def dispose_engine() -> None:
    """Close every pooled connection; used at shutdown and between test databases."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request.

    The session commits when the handler returns normally and rolls back on any exception,
    so every state change of a request lands in one transaction.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
