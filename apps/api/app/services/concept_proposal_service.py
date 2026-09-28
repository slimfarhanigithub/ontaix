"""Concept and specialisation proposals: the pending cell and its pending birth relation."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import ConceptDraft, SpecDraft
from app.models.storage.base import NodeKind, ProposalType, RelationKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.repositories import concept_repository, relation_repository
from app.services import outbox_service
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import (
    ISA_ACTION,
    ensure_can_propose,
    ensure_label_free,
    ensure_still_live,
    esc,
    store,
)
from app.utilities.clock import get_clock
from app.utilities.layout import birth_position, company_centre, domain_centre, rest_length
from app.utilities.permissions import Scope
from app.utilities.problems import not_found, validation_failed
from app.utilities.randomness import get_randomness

logger = logging.getLogger(__name__)


async def propose_concept(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ConceptDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    company, parent, product = _resolve_birth(
        view, draft.company_id, draft.parent_id, draft.parent_label, draft.domain_key
    )
    if enforce:
        ensure_can_propose(caller, Scope(company.id, product.template_key))
    await ensure_label_free(session, view, company.id, draft.label)
    await ensure_still_live(session, view, parent)
    template = view.templates[product.template_key]
    action = draft.action.strip().lower()
    concept, relation = await _divide(
        session,
        view,
        company,
        parent,
        product,
        draft.label,
        rule=None,
        isa=False,
        action=action,
        reverse=draft.reverse,
        seed=draft.seed,
    )
    label, parent_label, pred = esc(draft.label), esc(parent.label), esc(action)
    if draft.reverse:
        html_text = f"<b>{label}</b> <i>· {label} <b>{pred}</b> {parent_label}</i>"
    else:
        html_text = f"<b>{label}</b> <i>· {parent_label} <b>{pred}</b> {label}</i>"
    proposal = await store(
        session,
        proposer,
        view,
        type=ProposalType.CONCEPT,
        change_kind=None,
        title=draft.label,
        color=view.effective_color(template.key),
        company_id=company.id,
        domain_product_id=product.id,
        parent_label=parent.label,
        deps=[parent.label],
        wait_for=parent.label,
        html=html_text,
        why=f"domain product: {template.name}",
        caption=draft.caption,
        payload={},
        touched_company_ids=[company.id],
        concept_id=concept.id,
        relation_id=relation.id,
        bulk=bulk,
    )
    await _emit_born(session, proposer, view, proposal, concept, relation)
    return proposal


async def propose_spec(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: SpecDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    company, parent, product = _resolve_birth(
        view, draft.company_id, draft.parent_id, draft.parent_label, draft.domain_key
    )
    if enforce:
        ensure_can_propose(caller, Scope(company.id, product.template_key))
    await ensure_label_free(session, view, company.id, draft.label)
    await ensure_still_live(session, view, parent)
    template = view.templates[product.template_key]
    concept, relation = await _divide(
        session,
        view,
        company,
        parent,
        product,
        draft.label,
        rule=draft.rule,
        isa=True,
        action=ISA_ACTION,
        reverse=False,
        seed=draft.seed,
    )
    why = (f"rule: {draft.rule}" if draft.rule else "") + f" · domain product: {template.name}"
    proposal = await store(
        session,
        proposer,
        view,
        type=ProposalType.SPEC,
        change_kind=None,
        title=draft.label,
        color=view.effective_color(template.key),
        company_id=company.id,
        domain_product_id=product.id,
        parent_label=parent.label,
        deps=[parent.label],
        wait_for=parent.label,
        html=f"<b>{esc(draft.label)}</b> <i>is a {esc(parent.label)}</i>",
        why=why,
        caption=draft.caption,
        payload={},
        touched_company_ids=[company.id],
        concept_id=concept.id,
        relation_id=relation.id,
        bulk=bulk,
    )
    await _emit_born(session, proposer, view, proposal, concept, relation)
    return proposal


async def _divide(
    session: AsyncSession,
    view: OntologyView,
    company: Company,
    parent: Concept,
    product: Any,
    label: str,
    *,
    rule: str | None,
    isa: bool,
    action: str,
    reverse: bool,
    seed: float | None,
) -> tuple[Concept, Relation]:
    """Write the pending cell born from `parent` and its pending birth relation."""
    rng, clock = get_randomness(), get_clock()
    template = view.templates[product.template_key]
    company_xy = company_centre(company.position, len(view.companies))
    x, y = birth_position(
        (parent.x, parent.y), domain_centre(company_xy, template.position), rng.next()
    )
    concept = await concept_repository.create(
        session,
        tenant_id=view.tenant_id,
        company_id=company.id,
        kind=NodeKind.CONCEPT,
        label=label,
        sub=rule or "",
        domain_product_id=product.id,
        rule=rule,
        pending=True,
        parent_id=parent.id,
        birth_action=action,
        birth_reverse=reverse,
        born_at=clock.now(),
        x=x,
        y=y,
    )
    view.register_concept(concept)
    cross_domain = parent.domain_product_id != product.id
    kind = RelationKind.ISA if isa else RelationKind.REL
    a, b = (concept, parent) if (isa or reverse) else (parent, concept)
    relation = await relation_repository.create(
        session,
        tenant_id=view.tenant_id,
        a_id=a.id,
        b_id=b.id,
        kind=kind,
        label=action,
        rest=rest_length(kind.value, cross_domain, False),
        seed=seed if seed is not None else rng.next(),
        pending=True,
    )
    view.register_relation(relation)
    await concept_repository.set_birth_relation(session, concept, relation.id)
    return concept, relation


def _resolve_birth(
    view: OntologyView,
    company_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    parent_label: str | None,
    domain_key: str,
) -> tuple[Company, Concept, Any]:
    company = view.companies.get(company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if parent_id is not None:
        parent = view.concepts.get(parent_id)
        if parent is None or parent.company_id != company.id or parent.dying_at is not None:
            raise not_found("parent concept")
    else:
        parent = view.find_label(company.id, parent_label or "")
        if parent is None:
            raise not_found(f"parent concept {parent_label!r}")
    product = view.domain_product_by_key(company.id, domain_key)
    if product is None:
        raise validation_failed("domainKey", f"unknown domain key {domain_key!r}")
    return company, parent, product


async def _emit_born(
    session: AsyncSession,
    proposer: Actor,
    view: OntologyView,
    proposal: Proposal,
    concept: Concept,
    relation: Relation,
) -> None:
    await outbox_service.emit(
        session,
        view.tenant_id,
        proposer,
        "concept.born",
        {
            "concept": view.concept_dto(concept).model_dump(mode="json", by_alias=True),
            "birthRelation": view.relation_dto(relation).model_dump(mode="json", by_alias=True),
            "proposalId": str(proposal.id),
        },
        company_id=concept.company_id,
        bulk=proposal.bulk,
    )
