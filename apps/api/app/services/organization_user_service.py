"""An organization's members for the platform portal: list, create, add an existing account,
edit, remove, disable, enable and reset a password (platform role, super admin only).

A member is an account's membership of the organization, through the organization's directory
user (issuer `local`, subject `<account id>:<tenant id>`). Add user creates the account, the
user and the membership with an initial password the holder must change at first sign-in; Add
existing account adds a membership for an account that already exists, and gives back the same
directory user to an account removed from the organization earlier. Remove keeps the directory
user for history, drops the groups and ends the account's sessions inside this organization.
Disable and enable act on the membership alone; a password reset is for the account, so for
every organization of it. The password is never returned, logged or audited. Group memberships
are changed like the Groups page does: immediately, and audited as kind `groups` in the
organization's log.
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
    MembershipCreate,
    OrganizationUser,
    OrganizationUserCreate,
    OrganizationUserUpdate,
)
from app.models.api.page import PageOf
from app.models.storage.account import Account
from app.models.storage.account_membership import AccountMembership
from app.models.storage.app_user import AppUser
from app.models.storage.base import PasswordSetReason, SessionEndReason, ThrottleKeyKind
from app.models.storage.tenant import Tenant
from app.models.storage.user_group import UserGroup
from app.repositories import (
    account_membership_repository,
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
    organization_access_audit_service,
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

EMAIL_TAKEN = (
    "An account with this email already exists; add it to the organization with Add existing"
    " account"
)
DUPLICATE_EMAIL = "A user of the organization already has this email"
ACCOUNT_NOT_FOUND = "No member account has this email"
ALREADY_MEMBER = "This account is already a member of the organization"
ORGANIZATION_DISABLED = "The organization is disabled; enable it first"
FOREIGN_GROUP = "Choose groups of this organization only"
NO_SUCH_MEMBER = "No such member in this organization"


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
    raise ProblemError(404, "not_found", NO_SUCH_MEMBER)


async def create_user(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, body: OrganizationUserCreate
) -> OrganizationUser:
    """A new account with its first membership, directory user and initial password."""
    tenant = await _enabled(session, tenant_id)
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
    if await account_repository.get_by_email(session, email) is not None:
        raise conflict("email_taken", EMAIL_TAKEN)
    if await app_user_repository.email_taken(session, tenant_id, email):
        raise conflict("duplicate_email", DUPLICATE_EMAIL)
    password_hash = await password_hash_service.hash_password(body.password)
    account_id = uuid.uuid4()
    try:
        async with session.begin_nested():
            account = await account_repository.create(
                session,
                account_id=account_id,
                email=email,
                name=name,
                is_platform=False,
                created_by=admin.account_id,
            )
            user = await _join(session, account, tenant, name, _department(body.department))
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


async def add_membership(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, body: MembershipCreate
) -> OrganizationUser:
    """A membership of the organization for an existing member account. An account removed
    from the organization earlier gets its membership and directory user back, with the groups
    chosen now."""
    tenant = await _enabled(session, tenant_id)
    email = normalize_email(body.email)
    groups = await _groups_of(session, tenant_id, body.group_ids)
    account = await account_repository.get_by_email(session, email)
    if account is None or account.is_platform:
        raise ProblemError(404, "account_not_found", ACCOUNT_NOT_FOUND)
    membership = await account_membership_repository.get(session, account.id, tenant_id)
    if membership is not None and membership.removed_at is None:
        raise conflict("already_member", ALREADY_MEMBER)
    if membership is not None:
        await account_membership_repository.restore(session, account.id, tenant_id)
        user = await app_user_repository.get(session, tenant_id, membership.user_id)
        assert user is not None
    else:
        if await app_user_repository.email_taken(session, tenant_id, email):
            raise conflict("duplicate_email", DUPLICATE_EMAIL)
        try:
            async with session.begin_nested():
                user = await _join(session, account, tenant, account.name, None)
        except IntegrityError as exc:
            raise conflict("duplicate_email", DUPLICATE_EMAIL) from exc
    for group in groups:
        await group_member_repository.add(session, tenant_id, group.id, user.id)
        await _audit_membership(session, admin, tenant_id, user, group, added=True)
    await platform_audit_service.record(
        session,
        "membership_added",
        True,
        f"Account {email} added to the organization",
        actor_account_id=admin.account_id,
        target_account_id=account.id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )
    return await get_user(session, tenant_id, user.id)


async def remove_user(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Remove the member from the organization: the membership is marked removed, its groups
    go, and the account's sessions inside this organization end. The directory user, the
    account and its other memberships stay."""
    await require(session, tenant_id)
    membership, account, user = await _member(session, tenant_id, user_id)
    await account_membership_repository.remove(session, account.id, tenant_id)
    groups = {g.id: g for g in await user_group_repository.list_for_tenant(session, tenant_id)}
    for m in await group_member_repository.list_for_tenant(session, tenant_id):
        if m.user_id == user_id and m.group_id in groups:
            await group_member_repository.remove(session, tenant_id, m.group_id, user_id)
            await _audit_membership(
                session, admin, tenant_id, user, groups[m.group_id], added=False
            )
    await auth_session_repository.end_for_membership(
        session, account.id, tenant_id, SessionEndReason.MEMBERSHIP_REMOVED
    )
    await platform_audit_service.record(
        session,
        "membership_removed",
        True,
        f"Account {account.email} removed from the organization",
        actor_account_id=admin.account_id,
        target_account_id=account.id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )


async def update_user(
    session: AsyncSession,
    admin: PlatformAdmin,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OrganizationUserUpdate,
) -> OrganizationUser:
    """Rename the directory user (the name is per organization), change its department or
    replace its groups."""
    await require(session, tenant_id)
    _, account, user = await _member(session, tenant_id, user_id)
    fields = body.model_fields_set
    if not fields:
        raise ProblemError(422, "validation_failed", "Change at least one field")
    profile: dict[str, str | None] = {}
    if "name" in fields and body.name is not None:
        profile["name"] = body.name.strip()
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
    """Disable the membership (the account's sessions inside this organization end; its other
    organizations are untouched) or enable it; idempotent, audited on change."""
    await require(session, tenant_id)
    _, account, _ = await _member(session, tenant_id, user_id)
    if await account_membership_repository.set_disabled(session, account.id, tenant_id, disabled):
        if disabled:
            await auth_session_repository.end_for_membership(
                session, account.id, tenant_id, SessionEndReason.ACCOUNT_DISABLED
            )
        await platform_audit_service.record(
            session,
            "account_disabled" if disabled else "account_enabled",
            True,
            f"Account {account.email} {'disabled' if disabled else 'enabled'} in the organization",
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
    """Set the account's one password, for every organization of it, which the holder must
    change at next sign-in; every session of theirs ends and the lock on their email clears."""
    await require(session, tenant_id)
    _, account, _ = await _member(session, tenant_id, user_id)
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
    ended = await auth_session_repository.end_for_account(
        session, account.id, SessionEndReason.PASSWORD_RESET
    )
    await organization_access_audit_service.audit_ended(
        session,
        ended,
        organization_access_audit_service.PASSWORD_RESET_WHAT,
        admin.actor,
        client_ip=admin.client_ip,
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


def local_subject(account_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    """The subject of a member's directory user: one per account and organization, unique
    across every issuer."""
    return f"{account_id}:{tenant_id}"


async def _users(session: AsyncSession, tenant_id: uuid.UUID) -> list[OrganizationUser]:
    """The organization's members that are not removed, disabled ones included."""
    memberships = await account_membership_repository.list_for_tenant(session, tenant_id)
    accounts = {
        a.id: a
        for a in await account_repository.list_by_ids(session, {m.account_id for m in memberships})
    }
    credentials = await password_credential_repository.list_for_accounts(
        session, set(accounts.keys())
    )
    locked = await sign_in_throttle_repository.locked_keys(
        session, ThrottleKeyKind.EMAIL, {key_digest(a.email) for a in accounts.values()}
    )
    groups = {g.id: g for g in await user_group_repository.list_for_tenant(session, tenant_id)}
    group_refs: dict[uuid.UUID, list[GroupRef]] = {}
    for m in await group_member_repository.list_for_tenant(session, tenant_id):
        if m.group_id in groups:
            group_refs.setdefault(m.user_id, []).append(
                GroupRef(id=m.group_id, name=groups[m.group_id].name)
            )
    users = {u.id: u for u in await app_user_repository.list_for_tenant(session, tenant_id)}
    result = []
    for membership in memberships:
        account = accounts.get(membership.account_id)
        user = users.get(membership.user_id)
        if account is None or user is None:
            continue
        credential = credentials.get(account.id)
        result.append(
            OrganizationUser(
                id=user.id,
                account_id=account.id,
                email=account.email,
                name=user.name,
                department=user.department,
                status="disabled" if membership.disabled_at is not None else "active",
                must_change_password=bool(credential and credential.must_change),
                locked=key_digest(account.email) in locked,
                groups=sorted(group_refs.get(user.id, []), key=lambda g: g.name),
                created_at=membership.created_at,
                last_sign_in_at=user.last_login_at,
            )
        )
    return result


async def _member(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[AccountMembership, Account, AppUser]:
    """The membership behind the organization's directory user, with its account; 404 for a
    user who is no member, or one removed from the organization."""
    membership = await account_membership_repository.get_by_user(session, tenant_id, user_id)
    if membership is None or membership.removed_at is not None:
        raise ProblemError(404, "not_found", NO_SUCH_MEMBER)
    account = await account_repository.get(session, membership.account_id)
    user = await app_user_repository.get(session, tenant_id, user_id)
    if account is None or user is None:
        raise ProblemError(404, "not_found", NO_SUCH_MEMBER)
    return membership, account, user


async def _enabled(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await require(session, tenant_id)
    if tenant.disabled_at is not None:
        raise conflict("organization_disabled", ORGANIZATION_DISABLED)
    return tenant


async def _join(
    session: AsyncSession, account: Account, tenant: Tenant, name: str, department: str | None
) -> AppUser:
    """The account's directory user of the organization and its membership."""
    user = await app_user_repository.create(
        session,
        tenant_id=tenant.id,
        issuer=LOCAL_ISSUER,
        subject=local_subject(account.id, tenant.id),
        email=account.email,
        name=name,
        department=department,
        company_id=None,
    )
    await account_membership_repository.create(
        session, account_id=account.id, tenant_id=tenant.id, user_id=user.id
    )
    return user


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
