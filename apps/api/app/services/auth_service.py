"""Sign-in, sign-out, the current session and password change (platform role).

Sign-in checks, in order: the client IP's and the email's throttle (`429 sign_in_locked`), then
the argon2id verification. An unknown email is verified against a dummy hash and a disabled
account or organization is verified like any other, so a wrong password, an unknown email and a
disabled account or organization answer the same `401 invalid_credentials` after the same work.
Five failures within 15 minutes lock that email key and that IP key for 15 minutes, whether or
not an account has the email. Every attempt is audited; no entry names an email that matches no
account.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.session import Session as SessionDto
from app.models.storage.account import Account
from app.models.storage.base import PasswordSetReason, SessionEndReason, ThrottleKeyKind
from app.repositories import (
    account_repository,
    app_user_repository,
    auth_session_repository,
    password_credential_repository,
    sign_in_throttle_repository,
    tenant_repository,
)
from app.services import (
    organization_access_service,
    password_hash_service,
    password_policy_service,
    platform_audit_service,
    session_service,
)
from app.services.platform_audit_service import OrganizationCopy, member_actor
from app.services.session_service import IssuedSession, LiveSession
from app.utilities.problems import ProblemError
from app.utilities.session_tokens import is_well_formed, key_digest, normalize_email, token_digest

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Email or password is incorrect."
CURRENT_PASSWORD_INCORRECT = "Current password is incorrect."


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
    """A new session for valid credentials; the presented session, if any, ends."""
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
    if not verified or account is None or not await _may_sign_in(session, account):
        now_locked = await _record_failure(session, email_key, ip_key)
        await _audit_attempt(session, "sign_in_failed", account, attempt, "Sign-in failed")
        if now_locked:
            await _audit_attempt(
                session, "sign_in_locked", account, attempt, "Sign-in locked for 15 minutes"
            )
        await session.commit()
        raise ProblemError(401, "invalid_credentials", INVALID_CREDENTIALS)
    assert credential is not None
    await sign_in_throttle_repository.clear(session, ThrottleKeyKind.EMAIL, email_key)
    if password_hash_service.needs_rehash(credential.hash):
        await password_credential_repository.rehash(
            session, account.id, await password_hash_service.hash_password(password)
        )
    await _end_presented(session, presented_token)
    issued = await session_service.issue(
        session, account, client_ip=attempt.client_ip, user_agent=attempt.user_agent
    )
    await account_repository.touch_sign_in(session, account.id)
    if account.tenant_id is not None and account.user_id is not None:
        await app_user_repository.touch_login(session, account.tenant_id, account.user_id)
    await _audit_attempt(session, "sign_in", account, attempt, "Signed in", ok=True)
    return issued


async def sign_out(session: AsyncSession, live: LiveSession | None, attempt: Attempt) -> None:
    """End the live session, if any, and with it the organization a super admin had entered."""
    if live is None:
        return
    await auth_session_repository.end(session, live.row.id, SessionEndReason.SIGN_OUT)
    await _audit_attempt(session, "sign_out", live.account, attempt, "Signed out", ok=True)
    if live.resolved.acting_tenant_id is not None:
        await organization_access_service.audit_exit(
            session,
            platform_audit_service.platform_actor(live.account.id, live.account.name),
            live.resolved.acting_tenant_id,
            organization_access_service.SIGNED_OUT_WHAT,
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
        await _audit_attempt(session, "session_expired", account, attempt, "Session expired")
        if row.acting_tenant_id is not None:
            await organization_access_service.audit_exit(
                session,
                platform_audit_service.platform_actor(account.id, account.name),
                row.acting_tenant_id,
                organization_access_service.EXPIRED_WHAT,
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
            session, "password_change_failed", account, attempt, "Password change refused: policy"
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
    await auth_session_repository.end_for_account(
        session, account.id, SessionEndReason.PASSWORD_CHANGED
    )
    issued = await session_service.issue(
        session,
        account,
        client_ip=attempt.client_ip,
        user_agent=attempt.user_agent,
        rotates=live.row,
        support_tenant_id=live.resolved.support_tenant_id,
        acting_tenant_id=live.resolved.acting_tenant_id,
    )
    await _audit_attempt(session, "password_changed", account, attempt, "Password changed", ok=True)
    return issued


def password_rejected(detail: str, field: str) -> ProblemError:
    return ProblemError(
        422, "password_rejected", detail, errors=[{"field": field, "message": detail}]
    )


async def _may_sign_in(session: AsyncSession, account: Account) -> bool:
    if account.disabled_at is not None:
        return False
    if account.tenant_id is None:
        return True
    tenant = await tenant_repository.get(session, account.tenant_id)
    return tenant is not None and tenant.disabled_at is None


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
) -> None:
    """One platform entry, plus the organization's `auth` entry for a member's account. An
    attempt with an email no account has names no one."""
    copy = None
    if account is not None and account.tenant_id is not None and account.user_id is not None:
        copy = OrganizationCopy(
            tenant_id=account.tenant_id,
            actor=member_actor(account.user_id, account.name),
            kind="auth",
        )
    await platform_audit_service.record(
        session,
        action,
        ok,
        what,
        actor_account_id=account.id if account is not None else None,
        target_account_id=account.id if account is not None else None,
        target_tenant_id=account.tenant_id if account is not None else None,
        client_ip=attempt.client_ip,
        organization=copy,
    )
