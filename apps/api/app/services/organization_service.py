"""Organizations for the platform portal: list, create, rename, company mode, disable, enable.

Runs on the platform role. Creating an organization creates its tenant, company mode, default
settings, view state and five starter groups (each one role at tenant scope), and no company or
user. Disabling ends every session in the organization at once and keeps all of its data.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import PlatformAdmin
from app.models.api.group import Group, RoleAssignment, Scope
from app.models.api.organization import Organization, OrganizationCreate, OrganizationUpdate
from app.models.api.page import PageOf
from app.models.storage.base import CompanyMode, RoleName, ScopeKind
from app.models.storage.tenant import Tenant
from app.repositories import (
    account_repository,
    auth_session_repository,
    company_repository,
    group_member_repository,
    group_role_repository,
    organization_settings_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.services import organization_access_audit_service, outbox_service, platform_audit_service
from app.services.platform_audit_service import OrganizationCopy
from app.services.scene_service import settings_dto
from app.utilities.db_errors import constraint_name
from app.utilities.listing import ListQuery, matches_search, paginate
from app.utilities.problems import ProblemError, conflict

logger = logging.getLogger(__name__)

FILTERABLE = ("status", "companyMode")
SORTABLE = ("name", "createdAt", "users")
SLUG_MAX = 48
NON_SLUG = re.compile(r"[^a-z0-9]+")

STARTER_GROUPS: tuple[tuple[str, str, RoleName], ...] = (
    (
        "Administrators",
        "Administer the organization: settings, groups and roles.",
        RoleName.ADMINISTRATOR,
    ),
    ("Governors", "Approve and reject proposals across the organization.", RoleName.GOVERNOR),
    ("Builders", "Propose changes to the model.", RoleName.BUILDER),
    ("Members", "Read the model.", RoleName.MEMBER),
    ("Auditors", "Read the model, the directory and the audit log.", RoleName.AUDITOR),
)

DUPLICATE_ORGANIZATION = "Another organization already has this name"
COMPANY_MODE_REFUSED = "Remove companies until one is left before choosing One company"


async def list_organizations(session: AsyncSession, query: ListQuery) -> PageOf[Organization]:
    rows = await _organizations(session)
    selected = [
        o
        for o in rows
        if ("status" not in query.filters or o.status in query.filters["status"])
        and ("companyMode" not in query.filters or o.company_mode in query.filters["companyMode"])
        and matches_search(query.q, o.name, o.slug)
    ]
    page, total = paginate(
        selected,
        query,
        {
            "name": lambda o: o.name.lower(),
            "createdAt": lambda o: o.created_at,
            "users": lambda o: o.users,
        },
        "name",
    )
    return PageOf[Organization](items=page, page=query.page, page_size=query.page_size, total=total)


async def get_organization(session: AsyncSession, tenant_id: uuid.UUID) -> Organization:
    tenant = await require(session, tenant_id)
    return await _organization(session, tenant)


async def create_organization(
    session: AsyncSession, admin: PlatformAdmin, body: OrganizationCreate
) -> Organization:
    name = body.name.strip()
    if not name:
        raise ProblemError(422, "validation_failed", "Name the organization")
    if await tenant_repository.get_by_name(session, name) is not None:
        raise conflict("duplicate_organization", DUPLICATE_ORGANIZATION)
    try:
        async with session.begin_nested():
            tenant = await tenant_repository.create(session, await _free_slug(session, name), name)
    except IntegrityError as exc:
        raise conflict("duplicate_organization", DUPLICATE_ORGANIZATION) from exc
    mode = CompanyMode(body.company_mode)
    await tenant_settings_repository.create(session, tenant.id)
    await organization_settings_repository.create(session, tenant.id, mode)
    await view_state_repository.create(session, tenant.id)
    for group_name, description, role in STARTER_GROUPS:
        group = await user_group_repository.create(session, tenant.id, group_name, description)
        await group_role_repository.create(
            session,
            tenant_id=tenant.id,
            group_id=group.id,
            role=role,
            scope_kind=ScopeKind.TENANT,
            scope_company_id=None,
            scope_domain_key=None,
        )
    await platform_audit_service.record(
        session,
        "organization_created",
        True,
        f"Organization {name} created ({_mode_words(mode)})",
        actor_account_id=admin.account_id,
        target_tenant_id=tenant.id,
        client_ip=admin.client_ip,
    )
    return await _organization(session, tenant)


async def update_organization(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, body: OrganizationUpdate
) -> Organization:
    tenant = await require(session, tenant_id)
    if body.name is None and body.company_mode is None:
        raise ProblemError(422, "validation_failed", "Give a name or a company mode")
    copy = _copy(admin, tenant_id)
    if body.name is not None and body.name.strip() != tenant.name:
        name = body.name.strip()
        if not name:
            raise ProblemError(422, "validation_failed", "Name the organization")
        other = await tenant_repository.get_by_name(session, name)
        if other is not None and other.id != tenant_id:
            raise conflict("duplicate_organization", DUPLICATE_ORGANIZATION)
        old = tenant.name
        try:
            async with session.begin_nested():
                await tenant_repository.rename(session, tenant_id, name)
        except IntegrityError as exc:
            raise conflict("duplicate_organization", DUPLICATE_ORGANIZATION) from exc
        await platform_audit_service.record(
            session,
            "organization_renamed",
            True,
            f"Organization {old} renamed {name}",
            actor_account_id=admin.account_id,
            client_ip=admin.client_ip,
            organization=copy,
        )
    if body.company_mode is not None:
        await _set_company_mode(session, admin, tenant_id, CompanyMode(body.company_mode))
    return await get_organization(session, tenant_id)


async def set_disabled(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, disabled: bool
) -> Organization:
    """Disable (every session in it ends at once) or enable; idempotent, audited on change."""
    tenant = await require(session, tenant_id)
    if await tenant_repository.set_disabled(session, tenant_id, disabled):
        if disabled:
            ended = await auth_session_repository.end_for_tenant(session, tenant_id)
            await organization_access_audit_service.audit_ended(
                session,
                ended,
                organization_access_audit_service.ORGANIZATION_DISABLED_WHAT,
                admin.actor,
                client_ip=admin.client_ip,
            )
        await platform_audit_service.record(
            session,
            "organization_disabled" if disabled else "organization_enabled",
            True,
            f"Organization {tenant.name} {'disabled' if disabled else 'enabled'}",
            actor_account_id=admin.account_id,
            client_ip=admin.client_ip,
            organization=_copy(admin, tenant_id),
        )
    return await get_organization(session, tenant_id)


async def list_groups(session: AsyncSession, tenant_id: uuid.UUID) -> list[Group]:
    """The organization's groups with their roles, for the user dialogs' group picker."""
    await require(session, tenant_id)
    groups = await user_group_repository.list_for_tenant(session, tenant_id)
    roles = await group_role_repository.list_for_tenant(session, tenant_id)
    members = await group_member_repository.list_for_tenant(session, tenant_id)
    companies = {c.id: c.name for c in await company_repository.list_for_tenant(session, tenant_id)}
    return [
        Group(
            id=g.id,
            name=g.name,
            description=g.description,
            valid_until=g.valid_until,
            member_count=sum(1 for m in members if m.group_id == g.id),
            roles=[
                RoleAssignment(
                    id=r.id,
                    group_id=g.id,
                    role=r.role.value,
                    scope=Scope(
                        kind=r.scope_kind.value,
                        company_id=r.scope_company_id,
                        domain_key=r.scope_domain_key,
                        label=_scope_label(
                            r.scope_kind, r.scope_company_id, r.scope_domain_key, companies
                        ),
                    ),
                )
                for r in roles
                if r.group_id == g.id
            ],
        )
        for g in groups
    ]


async def require(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await tenant_repository.get(session, tenant_id)
    if tenant is None:
        raise ProblemError(404, "not_found", "No such organization")
    return tenant


async def _set_company_mode(
    session: AsyncSession, admin: PlatformAdmin, tenant_id: uuid.UUID, mode: CompanyMode
) -> None:
    before = await organization_settings_repository.get(session, tenant_id)
    if before is not None and before.company_mode is mode:
        return
    settings_before = await tenant_settings_repository.get(session, tenant_id)
    multi_before = bool(settings_before and settings_before.multi_company)
    try:
        async with session.begin_nested():
            if before is None:
                await organization_settings_repository.create(session, tenant_id, mode)
            else:
                await organization_settings_repository.set_company_mode(session, tenant_id, mode)
    except IntegrityError as exc:
        if constraint_name(exc) == "company_limit":
            raise conflict("company_limit", COMPANY_MODE_REFUSED) from exc
        raise
    settings_after = await tenant_settings_repository.get(session, tenant_id)
    changed = ["companyMode"]
    if multi_before and settings_after is not None and not settings_after.multi_company:
        changed.append("multiCompany")
    await outbox_service.emit(
        session,
        tenant_id,
        admin.actor,
        "settings.changed",
        {
            "settings": settings_dto(settings_after, mode).model_dump(mode="json", by_alias=True),
            "changed": changed,
        },
    )
    await platform_audit_service.record(
        session,
        "organization_company_mode",
        True,
        f"Companies set to {_mode_words(mode)}",
        actor_account_id=admin.account_id,
        client_ip=admin.client_ip,
        organization=_copy(admin, tenant_id),
    )


async def _organizations(session: AsyncSession) -> list[Organization]:
    tenants = await tenant_repository.list_all(session)
    users = await account_repository.count_by_tenant(session)
    companies = await company_repository.count_by_tenant(session)
    modes = await organization_settings_repository.modes(session)
    return [
        _dto(t, modes.get(t.id, CompanyMode.MULTIPLE), companies.get(t.id, 0), users.get(t.id, 0))
        for t in tenants
    ]


async def _organization(session: AsyncSession, tenant: Tenant) -> Organization:
    users = await account_repository.count_by_tenant(session)
    companies = await company_repository.count_by_tenant(session)
    mode = await organization_settings_repository.company_mode(session, tenant.id)
    return _dto(tenant, mode, companies.get(tenant.id, 0), users.get(tenant.id, 0))


def _dto(tenant: Tenant, mode: CompanyMode, companies: int, users: int) -> Organization:
    return Organization(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        company_mode=mode.value,
        status="disabled" if tenant.disabled_at is not None else "active",
        companies=companies,
        users=users,
        created_at=tenant.created_at,
        disabled_at=tenant.disabled_at,
    )


async def _free_slug(session: AsyncSession, name: str) -> str:
    """Lower-case, hyphens, at most 48 characters, never changed afterwards; a number is
    appended when another organization already has it."""
    base = NON_SLUG.sub("-", name.lower()).strip("-")[:SLUG_MAX].strip("-") or "organization"
    candidate, n = base, 1
    while await tenant_repository.slug_exists(session, candidate):
        n += 1
        suffix = f"-{n}"
        candidate = base[: SLUG_MAX - len(suffix)].strip("-") + suffix
    return candidate


def _copy(admin: PlatformAdmin, tenant_id: uuid.UUID) -> OrganizationCopy:
    return OrganizationCopy(tenant_id=tenant_id, actor=admin.actor, kind="platform")


def _mode_words(mode: CompanyMode) -> str:
    return "one company" if mode is CompanyMode.SINGLE else "several companies"


def _scope_label(
    kind: ScopeKind,
    company_id: uuid.UUID | None,
    domain_key: str | None,
    companies: dict[uuid.UUID, str],
) -> str:
    if kind is ScopeKind.TENANT:
        return "Tenant"
    if kind is ScopeKind.COMPANY and company_id is not None:
        return companies.get(company_id, "Company")
    return (domain_key or "").replace("_", " ").title()
