"""Builds the dev and test fixture tenant: directory, Northwind Industries, Aurora Valves and
their equivalences.

Every concept and relation goes through the proposal service and is approved through the
decision service, so the seeded state carries real audit entries, outbox rows and domain
product revisions. Seeding is idempotent: a tenant that already exists is left untouched.

The whole seed is one transaction, so the tenant's decision lock taken by the first approval is
held until the seed commits. That blocks nobody: the lock is keyed by tenant, the tenant row is
created in the same uncommitted transaction so no other request can reach it, and an existing
tenant is never seeded again.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ConceptDraft, RelationDraft, SpecDraft
from app.models.storage.app_user import AppUser
from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.seed import aurora, directory, northwind
from app.services import company_service, decision_service, proposal_service
from app.services.company_service import propose_starter_vocabulary
from app.services.ontology_view_service import load_view
from app.utilities.clock import get_clock
from app.utilities.permissions import Grant

logger = logging.getLogger(__name__)


async def seed_demo_tenant(session: AsyncSession) -> bool:
    """Create the fixture tenant with its data; returns False when it already exists."""
    if await tenant_repository.get_by_slug(session, directory.TENANT_SLUG) is not None:
        return False
    tenant = await tenant_repository.create(session, directory.TENANT_SLUG, directory.TENANT_NAME)
    await tenant_settings_repository.create(session, tenant.id)
    await view_state_repository.create(session, tenant.id)
    users = await _seed_directory(session, tenant.id)
    proposer = await _caller_for(session, users[directory.PROPOSER_EMAIL])
    approver = await _caller_for(session, users[directory.APPROVER_EMAIL])
    await _seed_northwind(session, proposer, approver)
    await _seed_aurora(session, proposer, approver)
    return True


async def _seed_directory(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, AppUser]:
    users: dict[str, AppUser] = {}
    for u in directory.USERS:
        users[u.email] = await app_user_repository.create(
            session,
            tenant_id=tenant_id,
            issuer=directory.DEV_ISSUER,
            subject=u.email,
            email=u.email,
            name=u.name,
            department=u.department,
            company_id=None,
        )
    for g in directory.GROUPS:
        group = await user_group_repository.create(session, tenant_id, g.name, g.description)
        for email in g.members:
            await group_member_repository.add(session, tenant_id, group.id, users[email].id)
        for r in g.roles:
            await group_role_repository.create(
                session,
                tenant_id=tenant_id,
                group_id=group.id,
                role=RoleName(r.role),
                scope_kind=ScopeKind(r.scope_kind),
                scope_company_id=None,
                scope_domain_key=r.scope_domain_key,
            )
    return users


async def _caller_for(session: AsyncSession, user: AppUser) -> Caller:
    assignments = await group_role_repository.list_for_user(
        session, user.tenant_id, user.id, get_clock().now()
    )
    return Caller(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name=user.name,
        grants=tuple(
            Grant(a.role, a.scope_kind, a.scope_company_id, a.scope_domain_key) for a in assignments
        ),
        everyone_teaches=False,
    )


async def _seed_northwind(session: AsyncSession, proposer: Caller, approver: Caller) -> None:
    view = await load_view(session, proposer.tenant_id)
    company = await company_service.add_company(
        session, view, northwind.COMPANY_NAME, northwind.COMPANY_SUB, is_home=True
    )
    for batch in northwind.BATCHES:
        created = [
            await proposal_service.create(session, proposer, view, _draft(company.id, row))
            for row in batch.rows
        ]
        for proposal in created:
            await decision_service.approve(session, approver, proposal.id, bulk=True)
        view = await load_view(session, proposer.tenant_id)


async def _seed_aurora(session: AsyncSession, proposer: Caller, approver: Caller) -> None:
    view = await load_view(session, proposer.tenant_id)
    company = await company_service.add_company(
        session, view, aurora.COMPANY_NAME, aurora.COMPANY_SUB, is_home=False
    )
    for proposal in await propose_starter_vocabulary(session, proposer, view, company):
        await decision_service.approve(session, approver, proposal.id, bulk=True)
    view = await load_view(session, proposer.tenant_id)
    northwind_company = next(c for c in view.companies.values() if c.is_home)
    for a_label, b_label in aurora.EQUIVALENCES:
        a = view.find_label(company.id, a_label)
        b = view.find_label(northwind_company.id, b_label)
        assert a is not None and b is not None
        caption = aurora.EQUIVALENCE_CAPTION.format(
            a=a.label, company_a=company.name, b=b.label, company_b=northwind_company.name
        )
        proposal = await proposal_service.propose_equivalence(
            session, proposer, view, a.id, b.id, caption
        )
        await decision_service.approve(session, approver, proposal.id, bulk=True)


def _draft(
    company_id: uuid.UUID, row: northwind.ConceptRow | northwind.SpecRow | northwind.RelationRow
) -> ConceptDraft | SpecDraft | RelationDraft:
    match row:
        case northwind.ConceptRow():
            return ConceptDraft(
                company_id=company_id,
                parent_label=row.parent,
                label=row.label,
                domain_key=row.domain,
                action=row.action,
                caption=row.caption,
            )
        case northwind.SpecRow():
            return SpecDraft(
                company_id=company_id,
                parent_label=row.parent,
                label=row.label,
                rule=row.rule,
                domain_key=row.domain,
                caption=row.caption,
            )
        case _:
            return RelationDraft(
                a_label=row.subject,
                b_label=row.object,
                company_id=company_id,
                action=row.action,
                caption=row.caption,
            )
