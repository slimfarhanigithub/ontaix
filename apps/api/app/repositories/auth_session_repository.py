"""Database access for the `auth_session` table and the `resolve_session()` function.

Times come from the database clock (`now()`), the same clock `resolve_session()` checks expiry
against. The application role reaches a session only through `resolve`; every other function
runs on the platform role.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, and_, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.account import Account
from app.models.storage.auth_session import AuthSession
from app.models.storage.base import SessionEndReason

IDLE_TIMEOUT = "30 minutes"
ABSOLUTE_TIMEOUT = "12 hours"
SUPPORT_DURATION = "60 minutes"
ACTING_DURATION = "60 minutes"

_CLOSE_EXPIRED_SUPPORT = text(
    "WITH expired AS ("
    " SELECT id, account_id, support_tenant_id FROM ontaix.auth_session"
    " WHERE support_tenant_id IS NOT NULL AND support_until <= now()"
    " FOR UPDATE SKIP LOCKED)"
    " UPDATE ontaix.auth_session s SET support_tenant_id = NULL, support_until = NULL"
    " FROM expired e WHERE s.id = e.id"
    " RETURNING s.id, e.account_id, e.support_tenant_id"
)
# Every acting row whose access has ended and is not yet audited, with the reason: the row
# ended, the hour of access or the session expired, the account or the organization was
# disabled, or the super admin role is gone.
_CLOSE_ENDED_ACCESS = text(
    "WITH done AS ("
    " SELECT s.id, s.account_id, s.acting_tenant_id,"
    " CASE WHEN s.ended_at IS NOT NULL THEN s.end_reason::text"
    " WHEN s.acting_until <= now() THEN 'access_expired'"
    " WHEN s.idle_expires_at <= now() OR s.absolute_expires_at <= now() THEN 'session_expired'"
    " WHEN a.disabled_at IS NOT NULL THEN 'account_disabled'"
    " WHEN t.disabled_at IS NOT NULL THEN 'organization_disabled'"
    " ELSE 'role_revoked' END AS reason"
    " FROM ontaix.auth_session s"
    " JOIN ontaix.account a ON a.id = s.account_id"
    " JOIN ontaix.tenant t ON t.id = s.acting_tenant_id"
    " WHERE s.acting_tenant_id IS NOT NULL AND s.acting_exited_at IS NULL"
    " AND (s.ended_at IS NOT NULL OR s.acting_until <= now()"
    " OR s.idle_expires_at <= now() OR s.absolute_expires_at <= now()"
    " OR a.disabled_at IS NOT NULL OR t.disabled_at IS NOT NULL"
    " OR NOT EXISTS (SELECT 1 FROM ontaix.platform_role_assignment r"
    " WHERE r.account_id = a.id AND r.role = 'super_admin'))"
    " FOR UPDATE OF s SKIP LOCKED)"
    " UPDATE ontaix.auth_session s SET acting_exited_at = now()"
    " FROM done d WHERE s.id = d.id"
    " RETURNING s.id, d.account_id, d.acting_tenant_id, d.reason"
)
_RESOLVE = text(
    "SELECT session_id, account_id, tenant_id, user_id, is_platform, support_tenant_id,"
    " acting_tenant_id, must_change_password, csrf_token"
    " FROM ontaix.resolve_session(:token_hash)"
)


@dataclass(frozen=True)
class ResolvedSession:
    """A live session as `resolve_session()` returns it."""

    session_id: uuid.UUID
    account_id: uuid.UUID
    tenant_id: uuid.UUID | None
    user_id: uuid.UUID | None
    is_platform: bool
    support_tenant_id: uuid.UUID | None
    acting_tenant_id: uuid.UUID | None
    must_change_password: bool
    csrf_token: str


@dataclass(frozen=True)
class EndedSession:
    """A session just ended: what the caller needs to audit the end of its platform access."""

    id: uuid.UUID
    account_id: uuid.UUID
    acting_tenant_id: uuid.UUID | None


async def resolve(session: AsyncSession, token_hash: bytes) -> ResolvedSession | None:
    """The live session of a token digest, sliding its idle expiry; None when there is none."""
    row = (await session.execute(_RESOLVE, {"token_hash": token_hash})).first()
    return None if row is None else ResolvedSession(*row)


async def get(session: AsyncSession, session_id: uuid.UUID) -> AuthSession | None:
    return await session.get(AuthSession, session_id, populate_existing=True)


async def get_by_token_hash(session: AsyncSession, token_hash: bytes) -> AuthSession | None:
    return await session.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .execution_options(populate_existing=True)
    )


async def get_timed_out(session: AsyncSession, token_hash: bytes) -> AuthSession | None:
    """The session of the digest when it has timed out without being ended, else None."""
    return await session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.ended_at.is_(None),
            (AuthSession.idle_expires_at <= func.now())
            | (AuthSession.absolute_expires_at <= func.now()),
        )
    )


async def create(
    session: AsyncSession,
    *,
    token_hash: bytes,
    csrf_token: str,
    account_id: uuid.UUID,
    client_ip: str | None,
    user_agent: str | None,
    absolute_expires_at: datetime | None = None,
    support_tenant_id: uuid.UUID | None = None,
    acting_tenant_id: uuid.UUID | None = None,
    acting_until: datetime | None = None,
) -> AuthSession:
    """A new live session. Without `absolute_expires_at` it ends 12 hours from now; a rotated
    session passes its predecessor's, so rotation never extends a session. A support session
    lasts 60 minutes, never past the absolute expiry. An acting session (a super admin inside
    `acting_tenant_id`) lasts 60 minutes too, or until `acting_until` when a rotated session
    passes its predecessor's, never past the absolute expiry."""
    assert support_tenant_id is None or acting_tenant_id is None
    absolute = (
        func.now() + text(f"interval '{ABSOLUTE_TIMEOUT}'")
        if absolute_expires_at is None
        else literal(absolute_expires_at)
    )
    idle = func.least(func.now() + text(f"interval '{IDLE_TIMEOUT}'"), absolute)
    support_until = (
        func.least(func.now() + text(f"interval '{SUPPORT_DURATION}'"), absolute)
        if support_tenant_id is not None
        else None
    )
    acting_until_at = None
    if acting_tenant_id is not None:
        acting_until_at = func.least(
            func.now() + text(f"interval '{ACTING_DURATION}'")
            if acting_until is None
            else literal(acting_until),
            absolute,
        )
    row = await session.execute(
        insert(AuthSession)
        .values(
            token_hash=token_hash,
            csrf_token=csrf_token,
            account_id=account_id,
            support_tenant_id=support_tenant_id,
            support_until=support_until,
            acting_tenant_id=acting_tenant_id,
            acting_until=acting_until_at,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
            client_ip=client_ip,
            user_agent=user_agent[:256] if user_agent else None,
        )
        .returning(AuthSession.id)
    )
    created = await get(session, row.scalar_one())
    assert created is not None
    return created


async def end(session: AsyncSession, session_id: uuid.UUID, reason: SessionEndReason) -> bool:
    """End one live session; False when it had already ended."""
    result = await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.ended_at.is_(None))
        .values(ended_at=func.now(), end_reason=reason)
        .returning(AuthSession.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def end_for_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    reason: SessionEndReason,
    keep: uuid.UUID | None = None,
) -> list[EndedSession]:
    """End every live session of the account except `keep`; the sessions ended."""
    conditions = [AuthSession.account_id == account_id, AuthSession.ended_at.is_(None)]
    if keep is not None:
        conditions.append(AuthSession.id != keep)
    result = await session.execute(
        update(AuthSession)
        .where(and_(*conditions))
        .values(ended_at=func.now(), end_reason=reason)
        .returning(AuthSession.id, AuthSession.account_id, AuthSession.acting_tenant_id)
        .execution_options(synchronize_session=False)
    )
    return [EndedSession(*row) for row in result.all()]


async def end_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[EndedSession]:
    """End every live session of the organization's accounts, every support session in it and
    every super admin session acting inside it; the sessions ended."""
    member_accounts = select(Account.id).where(Account.tenant_id == tenant_id)
    result = await session.execute(
        update(AuthSession)
        .where(
            AuthSession.ended_at.is_(None),
            AuthSession.account_id.in_(member_accounts)
            | (AuthSession.support_tenant_id == tenant_id)
            | (AuthSession.acting_tenant_id == tenant_id),
        )
        .values(ended_at=func.now(), end_reason=SessionEndReason.ORGANIZATION_DISABLED)
        .returning(AuthSession.id, AuthSession.account_id, AuthSession.acting_tenant_id)
        .execution_options(synchronize_session=False)
    )
    return [EndedSession(*row) for row in result.all()]


async def end_beyond_limit(
    session: AsyncSession, account_id: uuid.UUID, keep: int
) -> list[EndedSession]:
    """End the oldest live sessions of the account so that at most `keep` stay live; the
    sessions ended."""
    live = await session.execute(
        select(AuthSession.id, AuthSession.account_id, AuthSession.acting_tenant_id)
        .where(
            AuthSession.account_id == account_id,
            AuthSession.ended_at.is_(None),
            AuthSession.idle_expires_at > func.now(),
            AuthSession.absolute_expires_at > func.now(),
        )
        .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
    )
    surplus = [EndedSession(*row) for row in live.all()][keep:]
    for ended in surplus:
        await end(session, ended.id, SessionEndReason.SESSION_LIMIT)
    return surplus


async def mark_acting_exited(session: AsyncSession, session_id: uuid.UUID) -> bool:
    """Record that the end of the row's platform access is audited; False when it already
    was, or the row never acted inside an organization."""
    result = await session.execute(
        update(AuthSession)
        .where(
            AuthSession.id == session_id,
            AuthSession.acting_tenant_id.is_not(None),
            AuthSession.acting_exited_at.is_(None),
        )
        .values(acting_exited_at=func.now())
        .returning(AuthSession.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def close_ended_access(session: AsyncSession) -> list[Row]:
    """Mark every acting row whose access ended without being audited, returning (session id,
    account, organization, reason) of each; a concurrent sweep skips the rows another holds."""
    result = await session.execute(_CLOSE_ENDED_ACCESS)
    return list(result.all())


async def close_expired_support(session: AsyncSession) -> list[Row]:
    """Clear every support grant past its end, returning (session id, account, organization)
    of each one cleared; a concurrent sweep skips the rows another one holds."""
    result = await session.execute(_CLOSE_EXPIRED_SUPPORT)
    return list(result.all())
