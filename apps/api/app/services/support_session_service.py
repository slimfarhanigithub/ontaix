"""Read-only support sessions: a super admin's way to look at an organization's data.

Opening one replaces the presented session with a new token bound to the organization for 60
minutes, never past the session's absolute expiry; ending one replaces it with a token bound to
none. Inside it the super admin holds `model.read`, `directory.read` and `audit.read` at tenant
scope and nothing else. Start, end and expiry are written to the platform log and, as kind
`platform`, to the organization's own log.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import PlatformAdmin
from app.models.api.actor import Actor
from app.models.storage.base import SessionEndReason
from app.repositories import auth_session_repository
from app.services import organization_access_service, platform_audit_service, session_service
from app.services.organization_service import require
from app.services.platform_audit_service import OrganizationCopy
from app.services.session_service import IssuedSession
from app.utilities.problems import ProblemError, conflict

logger = logging.getLogger(__name__)

SYSTEM = Actor(kind="system")
ENDED = "Ended the read-only support session"
EXPIRED = "The read-only support session ended after 60 minutes"


async def start(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    reason: str,
    user_agent: str | None,
) -> IssuedSession:
    tenant = await require(session, tenant_id)
    if tenant.disabled_at is not None:
        raise conflict("organization_disabled", "The organization is disabled; enable it first")
    reason = " ".join(reason.split())
    if len(reason) < 3:
        raise ProblemError(
            422,
            "validation_failed",
            "Give a reason",
            errors=[{"field": "reason", "message": "Give a reason"}],
        )
    previous = admin.live.resolved.support_tenant_id
    acting = admin.live.resolved.acting_tenant_id
    await auth_session_repository.end(session, admin.live.row.id, SessionEndReason.SUPPORT_CHANGED)
    if previous is not None:
        await _audit_end(session, admin, previous, ENDED)
    if acting is not None:
        await organization_access_service.audit_exit(
            session,
            admin.actor,
            acting,
            organization_access_service.LEFT_WHAT,
            client_ip=admin.client_ip,
        )
    issued = await session_service.issue(
        session,
        admin.live.account,
        client_ip=admin.client_ip,
        user_agent=user_agent,
        rotates=admin.live.row,
        support_tenant_id=tenant_id,
    )
    await platform_audit_service.record(
        session,
        session_service.SUPPORT_STARTED,
        True,
        session_service.support_what(reason),
        actor_account_id=admin.account_id,
        client_ip=admin.client_ip,
        organization=OrganizationCopy(tenant_id=tenant_id, actor=admin.actor, kind="platform"),
    )
    return await _described(session, admin, issued)


async def end(
    session: AsyncSession, admin: PlatformAdmin, user_agent: str | None
) -> IssuedSession | None:
    """A new token without support; None when no support session was open."""
    previous = admin.live.resolved.support_tenant_id
    if previous is None:
        return None
    await auth_session_repository.end(session, admin.live.row.id, SessionEndReason.SUPPORT_CHANGED)
    issued = await session_service.issue(
        session,
        admin.live.account,
        client_ip=admin.client_ip,
        user_agent=user_agent,
        rotates=admin.live.row,
    )
    await _audit_end(session, admin, previous, ENDED)
    return issued


async def close_expired(session: AsyncSession) -> int:
    """Clear every support grant past its 60 minutes and audit each end, the system acting."""
    closed = await auth_session_repository.close_expired_support(session)
    for _, account_id, tenant_id in closed:
        await platform_audit_service.record(
            session,
            "support_session_ended",
            True,
            EXPIRED,
            target_account_id=account_id,
            organization=OrganizationCopy(tenant_id=tenant_id, actor=SYSTEM, kind="platform"),
        )
    return len(closed)


async def _audit_end(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, what: str
) -> None:
    await platform_audit_service.record(
        session,
        "support_session_ended",
        True,
        what,
        actor_account_id=admin.account_id,
        client_ip=admin.client_ip,
        organization=OrganizationCopy(tenant_id=tenant_id, actor=admin.actor, kind="platform"),
    )


async def _described(
    session: AsyncSession, admin: PlatformAdmin, issued: IssuedSession
) -> IssuedSession:
    """The session described again now that the start is audited, so it carries the reason."""
    return IssuedSession(
        token=issued.token,
        session=await session_service.describe(session, issued.row, admin.live.account),
        row=issued.row,
    )
