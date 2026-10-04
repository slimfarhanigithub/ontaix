"""The end of a super admin's platform access, audited exactly once however it ends.

An acting session (`auth_session.acting_tenant_id`) ends by an explicit exit, by entering another
organization or opening a support session, by sign-out, by a password change or reset, by the
account or the organization being disabled, by the session limit, or silently when the session
or the hour of access expires or the super admin role is revoked. Each path marks the row
(`acting_exited_at`) and writes `organization_exited` to the platform log and, as kind
`platform`, to the organization's log; a row already marked is never audited again. The upkeep
sweep (`close_ended`) catches every end no request path saw, with the system as actor.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.repositories import auth_session_repository
from app.repositories.auth_session_repository import EndedSession
from app.services import platform_audit_service
from app.services.platform_audit_service import OrganizationCopy

logger = logging.getLogger(__name__)

SYSTEM = Actor(kind="system")
EXITED = "organization_exited"
LEFT_WHAT = "Left the organization"
SIGNED_OUT_WHAT = "Left the organization: signed out"
EXPIRED_WHAT = "Left the organization: the session expired"
ACCESS_EXPIRED_WHAT = "Left the organization: the 60 minutes of access ended"
PASSWORD_CHANGED_WHAT = "Left the organization: the password was changed"
PASSWORD_RESET_WHAT = "Left the organization: the password was reset"
ACCOUNT_DISABLED_WHAT = "Left the organization: the account was disabled"
ORGANIZATION_DISABLED_WHAT = "Left the organization: the organization was disabled"
SESSION_LIMIT_WHAT = "Left the organization: the session limit ended the session"
ROLE_REVOKED_WHAT = "Left the organization: the super admin role was revoked"
# What the sweep writes, by the reason the row gives for the end of the access.
WHAT_BY_REASON = {
    "sign_out": SIGNED_OUT_WHAT,
    "password_changed": PASSWORD_CHANGED_WHAT,
    "password_reset": PASSWORD_RESET_WHAT,
    "account_disabled": ACCOUNT_DISABLED_WHAT,
    "organization_disabled": ORGANIZATION_DISABLED_WHAT,
    "session_limit": SESSION_LIMIT_WHAT,
    "support_changed": LEFT_WHAT,
    "access_changed": LEFT_WHAT,
    "access_expired": ACCESS_EXPIRED_WHAT,
    "session_expired": EXPIRED_WHAT,
    "role_revoked": ROLE_REVOKED_WHAT,
}


async def audit_exit(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    account_id: uuid.UUID,
    tenant_id: uuid.UUID,
    what: str,
    actor: Actor,
    client_ip: str | None = None,
) -> bool:
    """Mark the row's access as ended and audit it in both logs; False when it already was."""
    if not await auth_session_repository.mark_acting_exited(session, session_id):
        return False
    await platform_audit_service.record(
        session,
        EXITED,
        True,
        what,
        actor_account_id=actor.id if actor.kind == "platform" else None,
        target_account_id=account_id,
        client_ip=client_ip,
        organization=OrganizationCopy(tenant_id=tenant_id, actor=actor, kind="platform"),
    )
    return True


async def audit_ended(
    session: AsyncSession,
    ended: Iterable[EndedSession],
    what: str,
    actor: Actor,
    *,
    client_ip: str | None = None,
) -> int:
    """Audit the exit of every acting session among rows just ended; how many were audited."""
    audited = 0
    for row in ended:
        if row.acting_tenant_id is None:
            continue
        if await audit_exit(
            session,
            session_id=row.id,
            account_id=row.account_id,
            tenant_id=row.acting_tenant_id,
            what=what,
            actor=actor,
            client_ip=client_ip,
        ):
            audited += 1
    return audited


async def close_ended(session: AsyncSession) -> int:
    """Audit, the system acting, every access that ended without a request path seeing it."""
    closed = await auth_session_repository.close_ended_access(session)
    for _, account_id, tenant_id, reason in closed:
        await platform_audit_service.record(
            session,
            EXITED,
            True,
            WHAT_BY_REASON.get(reason, LEFT_WHAT),
            target_account_id=account_id,
            organization=OrganizationCopy(tenant_id=tenant_id, actor=SYSTEM, kind="platform"),
        )
    return len(closed)
