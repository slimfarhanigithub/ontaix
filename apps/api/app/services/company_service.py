"""Companies: reads, immediate creation with nine domain products and a root, removal proposals."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.company import Company as CompanyDto
from app.models.api.company import CompanyCreate, CompanyCreated
from app.models.api.drafts import ChangeDraft, ChangePayload, ConceptDraft
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.base import NodeKind
from app.models.storage.company import Company
from app.repositories import company_repository, concept_repository, domain_product_repository
from app.seed.starter_vocabulary import STARTER_VOCABULARY
from app.services import audit_service, outbox_service, proposal_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import charge_proposals
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.clock import get_clock
from app.utilities.layout import company_centre
from app.utilities.permissions import can_manage, can_read
from app.utilities.problems import conflict, forbidden, not_found
from app.utilities.slug import company_key

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = Actor(kind="system")


def readable_companies(caller: Caller, view: OntologyView) -> list[Company]:
    """Live companies of the tenant the caller may read, in display order."""
    return sorted(
        (
            c
            for c in view.companies.values()
            if c.dying_at is None and can_read(caller.grants, c.id)
        ),
        key=lambda c: c.position,
    )


async def list_companies(session: AsyncSession, caller: Caller) -> list[CompanyDto]:
    view = await load_view(session, caller.tenant_id)
    return [view.company_dto(c) for c in readable_companies(caller, view)]


async def get_company(session: AsyncSession, caller: Caller, company_id: uuid.UUID) -> CompanyDto:
    view = await load_view(session, caller.tenant_id)
    company = view.companies.get(company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if not can_read(caller.grants, company.id):
        raise forbidden("you may not read this company")
    return view.company_dto(company)


async def create_company(
    session: AsyncSession, caller: Caller, body: CompanyCreate
) -> CompanyCreated:
    """Immediate and audited: the company, its domain products, its root, then starter proposals."""
    if not can_manage(caller.grants):
        raise forbidden("adding a company requires Administrator")
    if body.start == "starter_vocabulary":
        charge_proposals(caller, len(STARTER_VOCABULARY))
    view = await load_view(session, caller.tenant_id)
    key = company_key(body.name)
    if any(c.key == key for c in view.companies.values()):
        raise conflict("duplicate_label", f"a company with key {key!r} already exists")
    company = await add_company(session, view, body.name, body.sub, is_home=not view.companies)
    root = view.root_of(company.id)
    assert root is not None
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        "company",
        f"{body.name} added",
        True,
        company_ids=[company.id],
    )
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "company.created",
        {
            "company": view.company_dto(company).model_dump(mode="json", by_alias=True),
            "root": view.concept_dto(root).model_dump(mode="json", by_alias=True),
        },
        company_ids=[company.id],
    )
    proposals: list[ProposalDto] = []
    if body.start == "starter_vocabulary":
        for proposal in await propose_starter_vocabulary(session, caller, view, company):
            proposals.append(
                readable_proposal(
                    caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
                )
            )
    return CompanyCreated(
        company=view.company_dto(company), root=view.concept_dto(root), proposals=proposals
    )


async def add_company(
    session: AsyncSession, view: OntologyView, name: str, sub: str, *, is_home: bool
) -> Company:
    """Write the company, its nine domain products and its root cell; no proposal involved."""
    position = await company_repository.next_position(session, view.tenant_id)
    company = await company_repository.create(
        session,
        view.tenant_id,
        key=company_key(name),
        name=name,
        sub=sub,
        position=position,
        is_home=is_home,
    )
    view.register_company(company)
    for template in view.templates.values():
        product = await domain_product_repository.create(
            session, view.tenant_id, company.id, template.key
        )
        view.register_domain_product(product)
    x, y = company_centre(position, len(view.companies))
    root = await concept_repository.create(
        session,
        tenant_id=view.tenant_id,
        company_id=company.id,
        kind=NodeKind.ROOT,
        label=name,
        sub=sub,
        domain_product_id=None,
        rule=None,
        pending=False,
        parent_id=None,
        birth_action=None,
        birth_reverse=False,
        born_at=get_clock().now(),
        x=x,
        y=y,
    )
    view.register_concept(root)
    return company


async def propose_starter_vocabulary(
    session: AsyncSession, caller: Caller, view: OntologyView, company: Company
) -> list:
    """The thirteen starter concepts, proposed by the system in the company's own words."""
    created = []
    for label, domain_key, action, parent_label in STARTER_VOCABULARY:
        domain_name = view.templates[domain_key].name
        draft = ConceptDraft(
            company_id=company.id,
            parent_label=parent_label or company.name,
            label=label,
            domain_key=domain_key,
            action=action,
            caption=f"{label} is kept in {company.name}’s {domain_name}.",
        )
        created.append(
            await proposal_service.create(
                session, caller, view, draft, enforce_permission=False, proposer=SYSTEM_ACTOR
            )
        )
    return created


async def propose_remove_company(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID
) -> ProposalDto:
    charge_proposals(caller)
    view = await load_view(session, caller.tenant_id)
    company = view.companies.get(company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    draft = ChangeDraft(change_kind="remove_company", payload=ChangePayload(company_id=company_id))
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )
