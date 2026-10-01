"""Server-side browser sessions: issue, find, describe and end them (platform role).

A session is a random 256-bit token in the `__Host-ontaix_session` cookie; the database keeps
only its SHA-256. It lives 30 minutes after the last authenticated call and never more than 12
hours after sign-in. Sign-in, a password change and the start or end of a support session each
issue a new token and end the old row, so a token never survives a change of privilege. An
account has at most 10 live sessions; the oldest ends first.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.organization import OrganizationRef
from app.models.api.session import Session as SessionDto
from app.models.api.session import SessionAccount, SupportInfo
from app.models.storage.account import Account
from app.models.storage.auth_session import AuthSession
from app.models.storage.tenant import Tenant
from app.repositories import (
    account_repository,
    auth_session_repository,
    password_credential_repository,
    platform_audit_repository,
    platform_role_repository,
    tenant_repository,
)
from app.repositories.auth_session_repository import ResolvedSession
from app.utilities.session_tokens import is_well_formed, new_token, token_digest

logger = logging.getLogger(__name__)

MAX_LIVE_SESSIONS = 10
SUPPORT_STARTED = "support_session_started"
SUPPORT_REASON_PREFIX = "Opened a read-only support session for 60 minutes. Reason: "


@dataclass(frozen=True)
class LiveSession:
    """A presented cookie that resolved to a live session, with its row and account."""

    resolved: ResolvedSession
    row: AuthSession
    account: Account


@dataclass(frozen=True)
class IssuedSession:
    """A new session: the token for the cookie (never logged or stored) and its description."""

    token: str
    session: SessionDto
    row: AuthSession


async def find_live(session: AsyncSession, token: str | None) -> LiveSession | None:
    """The live session of a presented cookie token, sliding its idle expiry; None otherwise."""
    if not is_well_formed(token):
        return None
    assert token is not None
    resolved = await auth_session_repository.resolve(session, token_digest(token))
    if resolved is None:
        return None
    row = await auth_session_repository.get(session, resolved.session_id)
    account = await account_repository.get(session, resolved.account_id)
    if row is None or account is None:
        return None
    return LiveSession(resolved=resolved, row=row, account=account)


async def issue(
    session: AsyncSession,
    account: Account,
    *,
    client_ip: str | None,
    user_agent: str | None,
    rotates: AuthSession | None = None,
    support_tenant_id: uuid.UUID | None = None,
) -> IssuedSession:
    """A new session for the account. `rotates` is the session it replaces, which the caller
    has ended: the new one keeps its absolute expiry, so rotation never lengthens a session."""
    await auth_session_repository.end_beyond_limit(session, account.id, MAX_LIVE_SESSIONS - 1)
    token = new_token()
    row = await auth_session_repository.create(
        session,
        token_hash=token_digest(token),
        csrf_token=new_token(),
        account_id=account.id,
        client_ip=client_ip,
        user_agent=user_agent,
        absolute_expires_at=rotates.absolute_expires_at if rotates is not None else None,
        support_tenant_id=support_tenant_id,
    )
    return IssuedSession(token=token, session=await describe(session, row, account), row=row)


async def describe(session: AsyncSession, row: AuthSession, account: Account) -> SessionDto:
    """The `Session` of the contract for a live row."""
    credential = await password_credential_repository.get(session, account.id)
    organization = None
    if account.tenant_id is not None:
        tenant = await tenant_repository.get(session, account.tenant_id)
        organization = _ref(tenant) if tenant is not None else None
    support = None
    if row.support_tenant_id is not None and row.support_until is not None:
        support_tenant = await tenant_repository.get(session, row.support_tenant_id)
        if support_tenant is not None:
            support = SupportInfo(
                organization=_ref(support_tenant),
                until=row.support_until,
                reason=await _support_reason(session, account.id, support_tenant.id),
            )
    roles = None
    if account.is_platform:
        roles = await platform_role_repository.roles_of(session, account.id)
    return SessionDto(
        kind="platform" if account.is_platform else "member",
        account=SessionAccount(id=account.id, email=account.email, name=account.name),
        organization=organization,
        user_id=account.user_id,
        platform_roles=[r.value for r in roles] if roles is not None else None,
        support=support,
        csrf_token=row.csrf_token,
        must_change_password=bool(credential and credential.must_change),
        idle_expires_at=row.idle_expires_at,
        absolute_expires_at=row.absolute_expires_at,
    )


def support_what(reason: str) -> str:
    """The audit sentence of a support session start; its reason is read back from it."""
    return SUPPORT_REASON_PREFIX + reason


async def _support_reason(
    session: AsyncSession, account_id: uuid.UUID, tenant_id: uuid.UUID
) -> str:
    entry = await platform_audit_repository.latest(session, SUPPORT_STARTED, account_id, tenant_id)
    if entry is None or not entry.what.startswith(SUPPORT_REASON_PREFIX):
        return ""
    return entry.what[len(SUPPORT_REASON_PREFIX) :]


def _ref(tenant: Tenant) -> OrganizationRef:
    return OrganizationRef(id=tenant.id, name=tenant.name, slug=tenant.slug)
