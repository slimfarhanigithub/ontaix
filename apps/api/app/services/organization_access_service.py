"""Platform access: a super admin enters an organization and acts inside it with every role.

Entering replaces the presented session with a new token bound to the organization through
`auth_session.acting_tenant_id`; leaving replaces it with a token bound to none. Inside, every
organization request runs as the super admin's directory user of that organization (issuer
`platform`, created at the first entry) with Administrator, Builder, Governor and Auditor at
tenant scope, on the application database role and under its row-level security, exactly as a
member's request. Entering and leaving are written to the platform log and, as kind `platform`,
to the organization's own log; the access also ends with the session, at sign-out or expiry,
which is audited the same way.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import PLATFORM_ISSUER, PlatformAdmin, platform_user_subject
from app.models.api.actor import Actor
from app.models.storage.account import Account
from app.models.storage.app_user import AppUser
from app.models.storage.base import SessionEndReason
from app.repositories import app_user_repository, auth_session_repository
from app.services import platform_audit_service, session_service
from app.services.organization_service import require
from app.services.platform_audit_service import OrganizationCopy
from app.services.session_service import IssuedSession
from app.utilities.problems import conflict

logger = logging.getLogger(__name__)

ENTERED = "organization_entered"
EXITED = "organization_exited"
ENTERED_WHAT = "Entered the organization as platform super admin, with every role"
LEFT_WHAT = "Left the organization"
SIGNED_OUT_WHAT = "Left the organization: signed out"
EXPIRED_WHAT = "Left the organization: the session expired"
SUPPORT_ENDED_WHAT = "Ended the read-only support session to enter the organization"


async def enter(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, user_agent: str | None
) -> IssuedSession:
    """A new token acting inside the organization; any support session or earlier entry ends."""
    tenant = await require(session, tenant_id)
    if tenant.disabled_at is not None:
        raise conflict("organization_disabled", "The organization is disabled; enable it first")
    await ensure_directory_user(session, tenant_id, admin.live.account)
    await auth_session_repository.end(session, admin.live.row.id, SessionEndReason.ACCESS_CHANGED)
    await _audit_previous_access(session, admin, LEFT_WHAT)
    issued = await session_service.issue(
        session,
        admin.live.account,
        client_ip=admin.client_ip,
        user_agent=user_agent,
        rotates=admin.live.row,
        acting_tenant_id=tenant_id,
    )
    await platform_audit_service.record(
        session,
        ENTERED,
        True,
        ENTERED_WHAT,
        actor_account_id=admin.account_id,
        client_ip=admin.client_ip,
        organization=OrganizationCopy(tenant_id=tenant_id, actor=admin.actor, kind="platform"),
    )
    return issued


async def leave(
    session: AsyncSession, admin: PlatformAdmin, user_agent: str | None
) -> IssuedSession | None:
    """A new token acting nowhere; None when the session was not inside an organization."""
    previous = admin.live.resolved.acting_tenant_id
    if previous is None:
        return None
    await auth_session_repository.end(session, admin.live.row.id, SessionEndReason.ACCESS_CHANGED)
    issued = await session_service.issue(
        session,
        admin.live.account,
        client_ip=admin.client_ip,
        user_agent=user_agent,
        rotates=admin.live.row,
    )
    await audit_exit(session, admin.actor, previous, LEFT_WHAT, client_ip=admin.client_ip)
    return issued


async def audit_exit(
    session: AsyncSession,
    actor: Actor,
    tenant_id: uuid.UUID,
    what: str,
    *,
    client_ip: str | None,
) -> None:
    """The end of an entry, in the platform log and the organization's log."""
    assert actor.id is not None
    await platform_audit_service.record(
        session,
        EXITED,
        True,
        what,
        actor_account_id=actor.id,
        client_ip=client_ip,
        organization=OrganizationCopy(tenant_id=tenant_id, actor=actor, kind="platform"),
    )


async def ensure_directory_user(
    session: AsyncSession, tenant_id: uuid.UUID, account: Account
) -> AppUser:
    """The super admin's directory user of the organization, created at the first entry."""
    subject = platform_user_subject(account.id, tenant_id)
    user = await app_user_repository.get_by_identity(session, PLATFORM_ISSUER, subject)
    if user is None:
        user = await app_user_repository.create(
            session,
            tenant_id=tenant_id,
            issuer=PLATFORM_ISSUER,
            subject=subject,
            email=account.email,
            name=account.name,
            department=None,
            company_id=None,
        )
    return user


async def _audit_previous_access(session: AsyncSession, admin: PlatformAdmin, what: str) -> None:
    """The end of whatever access the replaced session held: an entry or a support session."""
    resolved = admin.live.resolved
    if resolved.acting_tenant_id is not None:
        await audit_exit(
            session, admin.actor, resolved.acting_tenant_id, what, client_ip=admin.client_ip
        )
    if resolved.support_tenant_id is not None:
        await platform_audit_service.record(
            session,
            "support_session_ended",
            True,
            SUPPORT_ENDED_WHAT,
            actor_account_id=admin.account_id,
            client_ip=admin.client_ip,
            organization=OrganizationCopy(
                tenant_id=resolved.support_tenant_id, actor=admin.actor, kind="platform"
            ),
        )
