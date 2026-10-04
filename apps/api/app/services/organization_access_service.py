"""Platform access: a super admin enters an organization and acts inside it with every role.

Entering replaces the presented session with a new token bound to the organization through
`auth_session.acting_tenant_id` for 60 minutes (`acting_until`), never past the session's
absolute expiry; leaving replaces it with a token bound to none. Inside, every organization
request runs as the super admin's directory user of that organization (issuer `platform`,
created at the first entry) with Administrator, Builder, Governor and Auditor at tenant scope,
on the application database role and under its row-level security, exactly as a member's
request. Entering is written to the platform log and, as kind `platform`, to the organization's
own log; every way the access ends is audited through `organization_access_audit_service`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import PLATFORM_ISSUER, PlatformAdmin, platform_user_subject
from app.models.storage.account import Account
from app.models.storage.app_user import AppUser
from app.models.storage.base import SessionEndReason
from app.repositories import app_user_repository, auth_session_repository
from app.services import organization_access_audit_service, platform_audit_service, session_service
from app.services.organization_access_audit_service import LEFT_WHAT
from app.services.organization_service import require
from app.services.platform_audit_service import OrganizationCopy
from app.services.session_service import IssuedSession
from app.utilities.problems import conflict

logger = logging.getLogger(__name__)

ENTERED = "organization_entered"
ENTERED_WHAT = "Entered the organization as platform super admin, with every role for 60 minutes"
SUPPORT_ENDED_WHAT = "Ended the read-only support session to enter the organization"
SESSION_CHANGED_DETAIL = "The session changed while the request ran; reload the page and try again"
EMAIL_TAKEN_DETAIL = (
    "A user of the organization already has the super admin's email; change that user's email first"
)


async def enter(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, user_agent: str | None
) -> IssuedSession:
    """A new token acting inside the organization; any support session or earlier entry ends."""
    tenant = await require(session, tenant_id)
    if tenant.disabled_at is not None:
        raise conflict("organization_disabled", "The organization is disabled; enable it first")
    await ensure_directory_user(session, tenant_id, admin.live.account)
    await _end_presented(session, admin)
    await _audit_previous_access(session, admin)
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
    await _end_presented(session, admin)
    issued = await session_service.issue(
        session,
        admin.live.account,
        client_ip=admin.client_ip,
        user_agent=user_agent,
        rotates=admin.live.row,
    )
    await organization_access_audit_service.audit_exit(
        session,
        session_id=admin.live.row.id,
        account_id=admin.account_id,
        tenant_id=previous,
        what=LEFT_WHAT,
        actor=admin.actor,
        client_ip=admin.client_ip,
    )
    return issued


async def ensure_directory_user(
    session: AsyncSession, tenant_id: uuid.UUID, account: Account
) -> AppUser:
    """The super admin's directory user of the organization, created at the first entry. The
    organization's emails are unique, so another user with his email refuses the entry."""
    subject = platform_user_subject(account.id, tenant_id)
    user = await app_user_repository.get_by_identity(session, PLATFORM_ISSUER, subject)
    if user is not None:
        return user
    if await app_user_repository.email_taken(session, tenant_id, account.email):
        raise conflict("email_taken", EMAIL_TAKEN_DETAIL)
    return await app_user_repository.create(
        session,
        tenant_id=tenant_id,
        issuer=PLATFORM_ISSUER,
        subject=subject,
        email=account.email,
        name=account.name,
        department=None,
        company_id=None,
    )


async def _end_presented(session: AsyncSession, admin: PlatformAdmin) -> None:
    """End the presented session; a parallel request that ended it first wins."""
    ended = await auth_session_repository.end(
        session, admin.live.row.id, SessionEndReason.ACCESS_CHANGED
    )
    if not ended:
        raise conflict("session_changed", SESSION_CHANGED_DETAIL)


async def _audit_previous_access(session: AsyncSession, admin: PlatformAdmin) -> None:
    """The end of whatever access the replaced session held: an entry or a support session."""
    resolved = admin.live.resolved
    if resolved.acting_tenant_id is not None:
        await organization_access_audit_service.audit_exit(
            session,
            session_id=admin.live.row.id,
            account_id=admin.account_id,
            tenant_id=resolved.acting_tenant_id,
            what=LEFT_WHAT,
            actor=admin.actor,
            client_ip=admin.client_ip,
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
