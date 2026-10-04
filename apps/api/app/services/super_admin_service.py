"""The two bootstrap operations of the local admin CLI: create the super admin, set a password.

They run on a session of the schema owner's login, because only it may write
`platform_role_assignment`; no API path grants a platform role. Passwords arrive as arguments
from the CLI's no-echo prompt and are only ever hashed.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.storage.base import (
    PasswordSetReason,
    PlatformRoleName,
    SessionEndReason,
    ThrottleKeyKind,
)
from app.repositories import (
    account_repository,
    auth_session_repository,
    password_credential_repository,
    platform_role_repository,
    sign_in_throttle_repository,
)
from app.services import (
    organization_access_audit_service,
    password_hash_service,
    password_policy_service,
    platform_audit_service,
)
from app.services.platform_audit_service import OrganizationCopy
from app.utilities.session_tokens import key_digest, normalize_email

logger = logging.getLogger(__name__)

EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+$")
SYSTEM = Actor(kind="system")


class SuperAdminError(Exception):
    """A refusal the CLI prints as is; it never contains a password."""


async def create_super_admin(session: AsyncSession, email: str, password: str) -> uuid.UUID:
    """The platform account, its `super_admin` role and its password (no forced change)."""
    normalized = normalize_email(email)
    if not EMAIL_SHAPE.match(normalized) or len(normalized) > 254:
        raise SuperAdminError("That is not an email address.")
    if await account_repository.get_by_email(session, normalized) is not None:
        raise SuperAdminError("An account with this email already exists.")
    refusal = await password_policy_service.refusal(password, normalized)
    if refusal is not None:
        raise SuperAdminError(refusal)
    account = await account_repository.create(
        session,
        account_id=uuid.uuid4(),
        email=normalized,
        name=normalized.split("@", 1)[0],
        tenant_id=None,
        user_id=None,
        created_by=None,
    )
    await platform_role_repository.grant(session, account.id, PlatformRoleName.SUPER_ADMIN, None)
    await password_credential_repository.put(
        session,
        account.id,
        await password_hash_service.hash_password(password),
        PasswordSetReason.BOOTSTRAP,
        set_by=None,
    )
    await platform_audit_service.record(
        session,
        "super_admin_created",
        True,
        f"Super admin {normalized} created from the admin command line",
        actor_account_id=account.id,
        target_account_id=account.id,
    )
    return account.id


async def set_password(session: AsyncSession, email: str, password: str) -> None:
    """Set any account's password and end its sessions. A platform account's password needs no
    change at next sign-in; a member's, set by someone else, does."""
    normalized = normalize_email(email)
    account = await account_repository.get_by_email(session, normalized)
    if account is None:
        raise SuperAdminError("No account has this email.")
    credential = await password_credential_repository.get(session, account.id)
    refusal = await password_policy_service.refusal(
        password, normalized, credential.hash if credential else None
    )
    if refusal is not None:
        raise SuperAdminError(refusal)
    reason = PasswordSetReason.BOOTSTRAP if account.is_platform else PasswordSetReason.RESET
    await password_credential_repository.put(
        session,
        account.id,
        await password_hash_service.hash_password(password),
        reason,
        set_by=None,
    )
    ended = await auth_session_repository.end_for_account(
        session, account.id, SessionEndReason.PASSWORD_RESET
    )
    await organization_access_audit_service.audit_ended(
        session, ended, organization_access_audit_service.PASSWORD_RESET_WHAT, SYSTEM
    )
    await sign_in_throttle_repository.clear(session, ThrottleKeyKind.EMAIL, key_digest(normalized))
    copy = None
    if account.tenant_id is not None:
        copy = OrganizationCopy(tenant_id=account.tenant_id, actor=SYSTEM, kind="platform")
    await platform_audit_service.record(
        session,
        "super_admin_password_set",
        True,
        f"Password of {normalized} set from the admin command line",
        target_account_id=account.id,
        organization=copy,
    )
