"""Sign-in, sign-out, the current session, the choice of an organization, the portal language
and password change (platform role).

Sign-in checks, in order: the client IP's and the email's throttle (`429 sign_in_locked`), then
the argon2id verification. An unknown email is verified against a dummy hash and a disabled
account or organization is verified like any other, so a wrong password, an unknown email and a
disabled account or organization answer the same `401 invalid_credentials` after the same work.
Five failures within 15 minutes lock that email key and that IP key for 15 minutes, whether or
not an account has the email. After the password check a member enters its one active
organization directly, gets a session inside none when it has several (it then chooses one),
and is refused with `403 no_organization` when it belongs to none. Every attempt is audited; no
entry names an email that matches no account.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.session import Session as SessionDto
from app.models.storage.account import Account
from app.models.storage.base import PasswordSetReason, SessionEndReason, ThrottleKeyKind
from app.models.storage.tenant import Tenant
from app.repositories import (
    account_membership_repository,
    account_repository,
    app_user_repository,
    auth_session_repository,
    password_credential_repository,
    sign_in_throttle_repository,
)
from app.services import (
    organization_access_audit_service,
    password_hash_service,
    password_policy_service,
    platform_audit_service,
    session_service,
)
from app.services.platform_audit_service import OrganizationCopy, member_actor
from app.services.session_service import IssuedSession, LiveSession
from app.utilities.language import LANGUAGE_NAMES, Language
from app.utilities.problems import ProblemError, conflict, forbidden
from app.utilities.session_tokens import is_well_formed, key_digest, normalize_email, token_digest

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Email or password is incorrect."
CURRENT_PASSWORD_INCORRECT = "Current password is incorrect."
NO_ORGANIZATION = "Your account belongs to no organization. Ask your administrator."
NOT_YOUR_ORGANIZATION = "Choose one of your organizations"
PLATFORM_HAS_NO_ORGANIZATION = "A platform account enters an organization from the platform portal"
SESSION_CHANGED_DETAIL = "The session changed while the request ran; reload the page and try again"
ORGANIZATION_CHOSEN = "organization_chosen"


@dataclass(frozen=True)
class Attempt:
    """Where a sign-in or password change comes from."""

    client_ip: str | None
    user_agent: str | None


async def sign_in(
    session: AsyncSession,
    email: str,
    password: str,
    attempt: Attempt,
    presented_token: str | None,
) -> IssuedSession:
    """A new session for valid credentials; the presented session, if any, ends. A member's
    session is inside its one active organization, or inside none when it has several."""
    normalized = normalize_email(email)
    email_key = key_digest(normalized)
    ip_key = key_digest(attempt.client_ip) if attempt.client_ip else None
    locked = await _seconds_locked(session, email_key, ip_key)
    account = await account_repository.get_by_email(session, normalized)
    if locked:
        await _audit_attempt(session, "sign_in_locked", account, attempt, "Sign-in refused: locked")
        await session.commit()
        raise _locked(locked)
    credential = await password_credential_repository.get(session, account.id) if account else None
    verified = await password_hash_service.verify_password(
        credential.hash if credential else None, password
    )
    tenants = await _active_tenants(session, account) if account is not None else []
    if (
        not verified
        or account is None
        or account.disabled_at is not None
        or (not account.is_platform and not tenants and await _has_membership(session, account))
    ):
        now_locked = await _record_failure(session, email_key, ip_key)
        await _audit_attempt(session, "sign_in_failed", account, attempt, "Sign-in failed")
        if now_locked:
            await _audit_attempt(
                session, "sign_in_locked", account, attempt, "Sign-in locked for 15 minutes"
            )
        await session.commit()
        raise ProblemError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if not account.is_platform and not tenants:
        await _audit_attempt(
            session, "sign_in_failed", account, attempt, "Sign-in refused: no organization"
        )
        await session.commit()
        raise ProblemError(403, "no_organization", NO_ORGANIZATION)
    assert credential is not None
    await sign_in_throttle_repository.clear(session, ThrottleKeyKind.EMAIL, email_key)
    if password_hash_service.needs_rehash(credential.hash):
        await password_credential_repository.rehash(
            session, account.id, await password_hash_service.hash_password(password)
        )
    await _end_presented(session, presented_token)
    tenant_id = tenants[0].id if len(tenants) == 1 else None
    issued = await session_service.issue(
        session,
        account,
        client_ip=attempt.client_ip,
        user_agent=attempt.user_agent,
        tenant_id=tenant_id,
    )
    await account_repository.touch_sign_in(session, account.id)
    if tenant_id is not None:
        await _touch_login(session, account, tenant_id)
    await _audit_attempt(
        session, "sign_in", account, attempt, "Signed in", ok=True, tenant_id=tenant_id
    )
    return issued


async def choose_organization(
    session: AsyncSession,
    live: LiveSession,
    tenant_id: uuid.UUID,
    attempt: Attempt,
) -> IssuedSession:
    """A new token inside one of the member's organizations, chosen after a sign-in with
    several or to switch from the one the session is inside; the presented session ends."""
    account = live.account
    if account.is_platform:
        raise forbidden(PLATFORM_HAS_NO_ORGANIZATION)
    tenant = next((t for t in await _active_tenants(session, account) if t.id == tenant_id), None)
    if tenant is None:
        raise forbidden(NOT_YOUR_ORGANIZATION)
    ended = await auth_session_repository.end(session, live.row.id, SessionEndReason.ACCESS_CHANGED)
    if not ended:
        raise conflict("session_changed", SESSION_CHANGED_DETAIL)
    issued = await session_service.issue(
        session,
        account,
        client_ip=attempt.client_ip,
        user_agent=attempt.user_agent,
        rotates=live.row,
        tenant_id=tenant.id,
    )
    await _touch_login(session, account, tenant.id)
    await _audit_attempt(
        session,
        ORGANIZATION_CHOSEN,
        account,
        attempt,
        f"Entered {tenant.name}",
        ok=True,
        tenant_id=tenant.id,
    )
    return issued


async def sign_out(session: AsyncSession, live: LiveSession | None, attempt: Attempt) -> None:
    """End the live session, if any, and with it the organization a super admin had entered."""
    if live is None:
        return
    await auth_session_repository.end(session, live.row.id, SessionEndReason.SIGN_OUT)
    await _audit_attempt(
        session,
        "sign_out",
        live.account,
        attempt,
        "Signed out",
        ok=True,
        tenant_id=live.row.tenant_id,
    )
    if live.resolved.acting_tenant_id is not None:
        await organization_access_audit_service.audit_exit(
            session,
            session_id=live.row.id,
            account_id=live.account.id,
            tenant_id=live.resolved.acting_tenant_id,
            what=organization_access_audit_service.SIGNED_OUT_WHAT,
            actor=platform_audit_service.platform_actor(live.account.id, live.account.name),
            client_ip=attempt.client_ip,
        )


async def current(session: AsyncSession, live: LiveSession) -> SessionDto:
    return await session_service.describe(session, live.row, live.account)


async def record_expired(session: AsyncSession, token: str | None, attempt: Attempt) -> bool:
    """Audit a presented session that timed out without being ended; True when there was one,
    so the caller clears the cookie and the event is recorded once."""
    if not is_well_formed(token):
        return False
    assert token is not None
    row = await auth_session_repository.get_timed_out(session, token_digest(token))
    if row is None:
        return False
    account = await account_repository.get(session, row.account_id)
    if account is not None:
        await _audit_attempt(
            session, "session_expired", account, attempt, "Session expired", tenant_id=row.tenant_id
        )
        if row.acting_tenant_id is not None:
            await organization_access_audit_service.audit_exit(
                session,
                session_id=row.id,
                account_id=account.id,
                tenant_id=row.acting_tenant_id,
                what=organization_access_audit_service.EXPIRED_WHAT,
                actor=platform_audit_service.platform_actor(account.id, account.name),
                client_ip=attempt.client_ip,
            )
    return True


async def change_password(
    session: AsyncSession,
    live: LiveSession,
    current_password: str,
    new_password: str,
    attempt: Attempt,
) -> IssuedSession:
    """Change the signed-in account's own password. Every other session ends and this one gets
    a new token; the forced change, if any, is lifted."""
    account = live.account
    tenant_id = live.row.tenant_id
    email_key = key_digest(account.email)
    locked = await sign_in_throttle_repository.seconds_locked(
        session, ThrottleKeyKind.EMAIL, email_key
    )
    if locked:
        raise _locked(locked)
    credential = await password_credential_repository.get(session, account.id)
    if credential is None or not await password_hash_service.verify_password(
        credential.hash, current_password
    ):
        await sign_in_throttle_repository.record_failure(session, ThrottleKeyKind.EMAIL, email_key)
        await _audit_attempt(
            session,
            "password_change_failed",
            account,
            attempt,
            "Password change refused: current password incorrect",
            tenant_id=tenant_id,
        )
        await session.commit()
        raise ProblemError(
            422,
            "current_password_incorrect",
            CURRENT_PASSWORD_INCORRECT,
            errors=[{"field": "currentPassword", "message": CURRENT_PASSWORD_INCORRECT}],
        )
    refusal = await password_policy_service.refusal(new_password, account.email, credential.hash)
    if refusal is not None:
        await _audit_attempt(
            session,
            "password_change_failed",
            account,
            attempt,
            "Password change refused: policy",
            tenant_id=tenant_id,
        )
        await session.commit()
        raise password_rejected(refusal, "newPassword")
    await password_credential_repository.put(
        session,
        account.id,
        await password_hash_service.hash_password(new_password),
        PasswordSetReason.CHANGE,
        set_by=account.id,
    )
    ended = await auth_session_repository.end_for_account(
        session, account.id, SessionEndReason.PASSWORD_CHANGED
    )
    acting_tenant_id = live.resolved.acting_tenant_id
    if acting_tenant_id is not None:
        # The access continues on the new token, so this row's end is no exit.
        await auth_session_repository.mark_acting_exited(session, live.row.id)
    await organization_access_audit_service.audit_ended(
        session,
        ended,
        organization_access_audit_service.PASSWORD_CHANGED_WHAT,
        platform_audit_service.platform_actor(account.id, account.name),
        client_ip=attempt.client_ip,
    )
    issued = await session_service.issue(
        session,
        account,
        client_ip=attempt.client_ip,
        user_agent=attempt.user_agent,
        rotates=live.row,
        tenant_id=tenant_id,
        support_tenant_id=live.resolved.support_tenant_id,
        acting_tenant_id=acting_tenant_id,
        acting_until=live.row.acting_until if acting_tenant_id is not None else None,
    )
    await _audit_attempt(
        session,
        "password_changed",
        account,
        attempt,
        "Password changed",
        ok=True,
        tenant_id=tenant_id,
    )
    return issued


async def set_language(
    session: AsyncSession, live: LiveSession, language: Language | None, attempt: Attempt
) -> SessionDto:
    """The signed-in account's own portal language, or None to follow the browser; the session
    keeps its token. Audited as `account_updated`."""
    account = live.account
    await account_repository.set_language(session, account.id, language)
    updated = await account_repository.get(session, account.id)
    assert updated is not None
    what = (
        f"Language set to {LANGUAGE_NAMES[language]}"
        if language is not None
        else "Language follows the browser"
    )
    await _audit_attempt(
        session, "account_updated", updated, attempt, what, ok=True, tenant_id=live.row.tenant_id
    )
    return await session_service.describe(session, live.row, updated)


def password_rejected(detail: str, field: str) -> ProblemError:
    return ProblemError(
        422, "password_rejected", detail, errors=[{"field": field, "message": detail}]
    )


async def _active_tenants(session: AsyncSession, account: Account) -> list[Tenant]:
    """The enabled organizations the member may enter; none for a platform account."""
    if account.is_platform:
        return []
    return await account_membership_repository.active_tenants(session, account.id)


async def _has_membership(session: AsyncSession, account: Account) -> bool:
    """Whether the account belongs to any organization, its memberships there disabled or its
    organizations disabled or not; a removed membership does not count."""
    return bool(await account_membership_repository.list_for_account(session, account.id))


async def _touch_login(session: AsyncSession, account: Account, tenant_id: uuid.UUID) -> None:
    membership = await account_membership_repository.get(session, account.id, tenant_id)
    if membership is not None:
        await app_user_repository.touch_login(session, tenant_id, membership.user_id)


async def _seconds_locked(session: AsyncSession, email_key: bytes, ip_key: bytes | None) -> int:
    seconds = await sign_in_throttle_repository.seconds_locked(
        session, ThrottleKeyKind.EMAIL, email_key
    )
    if ip_key is not None:
        seconds = max(
            seconds,
            await sign_in_throttle_repository.seconds_locked(session, ThrottleKeyKind.IP, ip_key),
        )
    return seconds


async def _record_failure(session: AsyncSession, email_key: bytes, ip_key: bytes | None) -> bool:
    locked = await sign_in_throttle_repository.record_failure(
        session, ThrottleKeyKind.EMAIL, email_key
    )
    if ip_key is not None:
        locked = (
            await sign_in_throttle_repository.record_failure(session, ThrottleKeyKind.IP, ip_key)
            or locked
        )
    return locked


async def _end_presented(session: AsyncSession, token: str | None) -> None:
    """End the session the sign-in request presented, live or not, so no token is reused."""
    if not is_well_formed(token):
        return
    assert token is not None
    row = await auth_session_repository.get_by_token_hash(session, token_digest(token))
    if row is not None:
        await auth_session_repository.end(session, row.id, SessionEndReason.SIGN_OUT)


def _locked(seconds: int) -> ProblemError:
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return ProblemError(
        429,
        "sign_in_locked",
        f"Too many attempts. Try again in {minutes} {unit}.",
        headers={"Retry-After": str(seconds)},
    )


async def _audit_attempt(
    session: AsyncSession,
    action: str,
    account: Account | None,
    attempt: Attempt,
    what: str,
    *,
    ok: bool = False,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """One platform entry, plus the organization's `auth` entry for a member's account: in the
    organization the session is inside (`tenant_id`) when there is one, else in every
    organization the member belongs to. An attempt with an email no account has names no one."""
    copies = await _organization_copies(session, account, tenant_id)
    await platform_audit_service.record(
        session,
        action,
        ok,
        what,
        actor_account_id=account.id if account is not None else None,
        target_account_id=account.id if account is not None else None,
        target_tenant_id=tenant_id,
        client_ip=attempt.client_ip,
    )
    for copy in copies:
        await platform_audit_service.mirror(session, copy, what, ok)


async def _organization_copies(
    session: AsyncSession, account: Account | None, tenant_id: uuid.UUID | None
) -> list[OrganizationCopy]:
    if account is None or account.is_platform:
        return []
    return [
        OrganizationCopy(
            tenant_id=membership.tenant_id, actor=member_actor(user.id, user.name), kind="auth"
        )
        for membership, user in await account_membership_repository.list_users_for_account(
            session, account.id
        )
        if tenant_id is None or membership.tenant_id == tenant_id
    ]
