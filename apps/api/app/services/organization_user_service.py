"""An organization's accounts for the platform portal: list, create, edit, disable, enable and
reset a password (platform role, super admin only).

An account is created with its directory user (issuer `local`, subject the account id) and an
initial password the user must change at first sign-in. The password is never returned, logged
or audited. Group memberships are changed like the Groups page does: immediately, and audited
as kind `groups` in the organization's log.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import PlatformAdmin
from app.models.api.organization_user import (
    GroupRef,
    OrganizationUser,
    OrganizationUserCreate,
    OrganizationUserUpdate,
)
from app.models.api.page import PageOf
from app.models.storage.account import Account
from app.models.storage.app_user import AppUser
from app.models.storage.base import PasswordSetReason, SessionEndReason, ThrottleKeyKind
from app.models.storage.user_group import UserGroup
from app.repositories import (
    account_repository,
    app_user_repository,
    auth_session_repository,
    group_member_repository,
    password_credential_repository,
    sign_in_throttle_repository,
    user_group_repository,
)
from app.services import (
    audit_service,
    password_hash_service,
    password_policy_service,
    platform_audit_service,
)
from app.services.auth_service import password_rejected
from app.services.organization_service import require
from app.services.platform_audit_service import OrganizationCopy
from app.utilities.listing import ListQuery, matches_search, paginate
from app.utilities.problems import ProblemError, conflict
from app.utilities.session_tokens import key_digest, normalize_email

logger = logging.getLogger(__name__)

FILTERABLE = ("status", "inGroup")
SORTABLE = ("name", "email", "lastSignInAt")
LOCAL_ISSUER = "local"
EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+$")

DUPLICATE_EMAIL = "An account with this email already exists"
ORGANIZATION_DISABLED = "The organization is disabled; enable it first"
FOREIGN_GROUP = "Choose groups of this organization only"


async def list_users(
    session: AsyncSession, tenant_id: uuid.UUID, query: ListQuery
) -> PageOf[OrganizationUser]:
    await require(session, tenant_id)
    users = await _users(session, tenant_id)
    wanted = query.filters.get("status")
    in_group = set(query.filters.get("inGroup", []))
    selected = [
        u
        for u in users
        if (not wanted or any(_has_status(u, s) for s in wanted))
        and (not in_group or any(str(g.id) in in_group for g in u.groups))
        and matches_search(query.q, u.name, u.email)
    ]
    page, total = paginate(
        selected,
        query,
        {
            "name": lambda u: u.name.lower(),
            "email": lambda u: u.email,
            "lastSignInAt": lambda u: (
                u.last_sign_in_at or datetime.min.replace(tzinfo=u.created_at.tzinfo)
            ),
        },
        "name",
    )
    return PageOf[OrganizationUser](
        items=page, page=query.page, page_size=query.page_size, total=total
    )


async def get_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationUser:
    await require(session, tenant_id)
    for user in await _users(session, tenant_id):
        if user.id == user_id:
            return user
    raise ProblemError(404, "not_found", "No such account in this organization")


async def create_user(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, body: OrganizationUserCreate
) -> OrganizationUser:
    tenant = await require(session, tenant_id)
    if tenant.disabled_at is not None:
        raise conflict("organization_disabled", ORGANIZATION_DISABLED)
    email = normalize_email(body.email)
    if not EMAIL_SHAPE.match(email):
        raise ProblemError(
            422,
            "validation_failed",
            "Enter an email address",
            errors=[{"field": "email", "message": "Enter an email address"}],
        )
    name = body.name.strip()
    groups = await _groups_of(session, tenant_id, body.group_ids)
    refusal = await password_policy_service.refusal(body.password, email)
    if refusal is not None:
        raise password_rejected(refusal, "password")
    if await account_repository.get_by_email(
        session, email
    ) is not None or await app_user_repository.email_taken(session, tenant_id, email):
        raise conflict("duplicate_email", DUPLICATE_EMAIL)
    password_hash = await password_hash_service.hash_password(body.password)
    account_id = uuid.uuid4()
    try:
        async with session.begin_nested():
            user = await app_user_repository.create(
                session,
                tenant_id=tenant_id,
                issuer=LOCAL_ISSUER,
                subject=str(account_id),
                email=email,
                name=name,
                department=_department(body.department),
                company_id=None,
            )
            account = await account_repository.create(
                session,
                account_id=account_id,
                email=email,
                name=name,
                tenant_id=tenant_id,
                user_id=user.id,
                created_by=admin.account_id,
            )
    except IntegrityError as exc:
        raise conflict("duplicate_email", DUPLICATE_EMAIL) from exc
    await password_credential_repository.put(
        session, account.id, password_hash, PasswordSetReason.INITIAL, set_by=admin.account_id
    )
    for group in groups:
        await group_member_repository.add(session, tenant_id, group.id, user.id)
        await _audit_membership(session, admin, tenant_id, user, group, added=True)
    await platform_audit_service.record(
        session,
        "account_created",
        True,
        f"Account {email} created",
        actor_account_id=admin.account_id,
        target_account_id=account.id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )
    return await get_user(session, tenant_id, user.id)


async def update_user(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OrganizationUserUpdate,
) -> OrganizationUser:
    await require(session, tenant_id)
    account, user = await _account(session, tenant_id, user_id)
    fields = body.model_fields_set
    if not fields:
        raise ProblemError(422, "validation_failed", "Change at least one field")
    profile: dict[str, str | None] = {}
    if "name" in fields and body.name is not None:
        profile["name"] = body.name.strip()
        await account_repository.rename(session, account.id, body.name.strip())
    if "department" in fields:
        profile["department"] = _department(body.department)
    if profile:
        await app_user_repository.update_profile(session, tenant_id, user_id, profile)
    if "group_ids" in fields and body.group_ids is not None:
        wanted = {g.id: g for g in await _groups_of(session, tenant_id, body.group_ids)}
        current = {
            m.group_id
            for m in await group_member_repository.list_for_tenant(session, tenant_id)
            if m.user_id == user_id
        }
        groups = {g.id: g for g in await user_group_repository.list_for_tenant(session, tenant_id)}
        for group_id in current - wanted.keys():
            await group_member_repository.remove(session, tenant_id, group_id, user_id)
            await _audit_membership(session, admin, tenant_id, user, groups[group_id], added=False)
        for group_id in wanted.keys() - current:
            await group_member_repository.add(session, tenant_id, group_id, user_id)
            await _audit_membership(session, admin, tenant_id, user, wanted[group_id], added=True)
    await platform_audit_service.record(
        session,
        "account_updated",
        True,
        f"Account {account.email} updated",
        actor_account_id=admin.account_id,
        target_account_id=account.id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )
    return await get_user(session, tenant_id, user_id)


async def set_disabled(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    disabled: bool,
) -> OrganizationUser:
    """Disable (every session of the account ends) or enable; idempotent, audited on change."""
    await require(session, tenant_id)
    account, _ = await _account(session, tenant_id, user_id)
    if await account_repository.set_disabled(session, account.id, disabled):
        if disabled:
            await auth_session_repository.end_for_account(
                session, account.id, SessionEndReason.ACCOUNT_DISABLED
            )
        await platform_audit_service.record(
            session,
            "account_disabled" if disabled else "account_enabled",
            True,
            f"Account {account.email} {'disabled' if disabled else 'enabled'}",
            actor_account_id=admin.account_id,
            target_account_id=account.id,
            client_ip=admin.client_ip,
            organization=_copy(admin, tenant_id),
        )
    return await get_user(session, tenant_id, user_id)


async def reset_password(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    new_password: str,
) -> None:
    """Set a password the user must change at next sign-in; every session of theirs ends and
    the lock on their email clears."""
    await require(session, tenant_id)
    account, _ = await _account(session, tenant_id, user_id)
    credential = await password_credential_repository.get(session, account.id)
    refusal = await password_policy_service.refusal(
        new_password, account.email, credential.hash if credential else None
    )
    if refusal is not None:
        raise password_rejected(refusal, "newPassword")
    await password_credential_repository.put(
        session,
        account.id,
        await password_hash_service.hash_password(new_password),
        PasswordSetReason.RESET,
        set_by=admin.account_id,
    )
    await auth_session_repository.end_for_account(
        session, account.id, SessionEndReason.PASSWORD_RESET
    )
    await sign_in_throttle_repository.clear(
        session, ThrottleKeyKind.EMAIL, key_digest(account.email)
    )
    await platform_audit_service.record(
        session,
        "password_reset",
        True,
        f"Password of {account.email} reset",
        actor_account_id=admin.account_id,
        target_account_id=account.id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )


async def _users(session: AsyncSession, tenant_id: uuid.UUID) -> list[OrganizationUser]:
    accounts = await account_repository.list_for_tenant(session, tenant_id)
    credentials = await password_credential_repository.list_for_accounts(
        session, {a.id for a in accounts}
    )
    locked = await sign_in_throttle_repository.locked_keys(
        session, ThrottleKeyKind.EMAIL, {key_digest(a.email) for a in accounts}
    )
    groups = {g.id: g for g in await user_group_repository.list_for_tenant(session, tenant_id)}
    memberships: dict[uuid.UUID, list[GroupRef]] = {}
    for m in await group_member_repository.list_for_tenant(session, tenant_id):
        if m.group_id in groups:
            memberships.setdefault(m.user_id, []).append(
                GroupRef(id=m.group_id, name=groups[m.group_id].name)
            )
    users = {u.id: u for u in await app_user_repository.list_for_tenant(session, tenant_id)}
    result = []
    for account in accounts:
        assert account.user_id is not None
        user = users.get(account.user_id)
        credential = credentials.get(account.id)
        result.append(
            OrganizationUser(
                id=account.user_id,
                account_id=account.id,
                email=account.email,
                name=account.name,
                department=user.department if user else None,
                status="disabled" if account.disabled_at is not None else "active",
                must_change_password=bool(credential and credential.must_change),
                locked=key_digest(account.email) in locked,
                groups=sorted(memberships.get(account.user_id, []), key=lambda g: g.name),
                created_at=account.created_at,
                last_sign_in_at=account.last_sign_in_at,
            )
        )
    return result


async def _account(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Account, AppUser]:
    account = await account_repository.get_member(session, tenant_id, user_id)
    user = await app_user_repository.get(session, tenant_id, user_id)
    if account is None or user is None:
        raise ProblemError(404, "not_found", "No such account in this organization")
    return account, user


async def _groups_of(
    session: AsyncSession, tenant_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> list[UserGroup]:
    groups = {g.id: g for g in await user_group_repository.list_for_tenant(session, tenant_id)}
    unique = list(dict.fromkeys(group_ids))
    if any(g not in groups for g in unique):
        raise ProblemError(
            422,
            "validation_failed",
            FOREIGN_GROUP,
            errors=[{"field": "groupIds", "message": FOREIGN_GROUP}],
        )
    return [groups[g] for g in unique]


async def _audit_membership(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    user: AppUser,
    group: UserGroup,
    *,
    added: bool,
) -> None:
    what = (
        f"{user.name} added to {group.name}" if added else f"{user.name} removed from {group.name}"
    )
    await audit_service.record(
        session, tenant_id, admin.actor, "groups", what, True, company_ids=[]
    )


def _has_status(user: OrganizationUser, status: str) -> bool:
    if status == "mustChangePassword":
        return user.must_change_password
    if status == "locked":
        return user.locked
    return user.status == status


def _department(value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


def _copy(admin: PlatformAdmin, tenant_id: uuid.UUID) -> OrganizationCopy:
    return OrganizationCopy(tenant_id=tenant_id, actor=admin.actor, kind="platform")
