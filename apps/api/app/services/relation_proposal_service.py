"""Relation and equivalence proposals: the pending relation between two existing concepts.

A relation between two companies is a tenant-level proposal: it carries no company and no domain
product, so only a tenant-wide grant approves it, and proposing it needs a grant on both ends.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import RelationDraft
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.base import ProposalType, RelationKind
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import relation_repository
from app.services import outbox_service
from app.services.ontology_view_service import PREDICATE_BOTH_ENDS_APPROVED, OntologyView
from app.services.proposal_store_service import (
    ISA_ACTION,
    SAME_ACTION,
    ensure_can_propose,
    ensure_still_live,
    esc,
    store,
)
from app.utilities.layout import NEUTRAL_COLOR, rest_length
from app.utilities.permissions import Scope
from app.utilities.problems import conflict, not_found, validation_failed
from app.utilities.randomness import get_randomness

logger = logging.getLogger(__name__)


async def propose_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: RelationDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    a = _resolve_end(view, draft.a_id, draft.a_label, draft.company_id)
    b = _resolve_end(view, draft.b_id, draft.b_label, draft.company_id)
    if a.id == b.id:
        raise validation_failed("bId", "a relation needs two different concepts")
    action = draft.action.strip().lower()
    cross_company = a.company_id != b.company_id
    if cross_company and not (view.settings and view.settings.cross_company):
        raise conflict(
            "cross_company_disabled", "companies may not interact · enable it in the admin portal"
        )
    if enforce:
        ensure_can_propose(caller, Scope(a.company_id, view.domain_key(a)))
        if cross_company:
            ensure_can_propose(caller, Scope(b.company_id, view.domain_key(b)))
    if any(
        r.a_id == a.id and r.b_id == b.id and r.label.lower() == action
        for r in view.live_relations()
    ):
        raise conflict(
            "duplicate_relation", f"{a.label} {action} {b.label} is already in the model"
        )
    await ensure_still_live(session, view, a)
    await ensure_still_live(session, view, b)
    kind = _relation_kind(action)
    cross_domain = a.domain_product_id != b.domain_product_id
    relation = await relation_repository.create(
        session,
        tenant_id=view.tenant_id,
        a_id=a.id,
        b_id=b.id,
        kind=kind,
        label=action,
        rest=rest_length(kind.value, cross_domain, cross_company),
        seed=draft.seed if draft.seed is not None else get_randomness().next(),
        pending=True,
    )
    view.register_relation(relation)
    company_a, company_b = view.companies[a.company_id], view.companies[b.company_id]
    a_text = esc(a.label) + (f" <i>({esc(company_a.name)})</i>" if cross_company else "")
    b_text = esc(b.label) + (f" <i>({esc(company_b.name)})</i>" if cross_company else "")
    if cross_company:
        why = f"across companies: {company_a.name} ↔ {company_b.name}"
    elif cross_domain:
        why = (
            f"across domain products: {view.domain_name(a) or 'company'}"
            f" → {view.domain_name(b) or 'company'}"
        )
    else:
        why = f"inside {view.domain_name(a) or 'the company'}"
    proposal = await store(
        session,
        proposer,
        view,
        type=ProposalType.RELATION,
        change_kind=None,
        title=f"{a.label} {action} {b.label}",
        color=NEUTRAL_COLOR,
        company_id=None if cross_company else a.company_id,
        domain_product_id=None if cross_company else a.domain_product_id,
        parent_label=None,
        deps=[PREDICATE_BOTH_ENDS_APPROVED],
        wait_for=f"{a.label} and {b.label}",
        html=f"{a_text} <b>{esc(action)}</b> {b_text}",
        why=why,
        caption=draft.caption,
        payload={},
        touched_company_ids=[a.company_id, b.company_id],
        concept_id=None,
        relation_id=relation.id,
        bulk=bulk,
        provenance=provenance,
    )
    await outbox_service.emit(
        session,
        view.tenant_id,
        proposer,
        "relation.created",
        {
            "relation": view.relation_dto(relation).model_dump(mode="json", by_alias=True),
            "proposalId": str(proposal.id),
        },
        company_ids=[a.company_id, b.company_id],
        bulk=bulk,
    )
    return proposal


def _resolve_end(
    view: OntologyView,
    concept_id: uuid.UUID | None,
    label: str | None,
    company_id: uuid.UUID | None,
) -> Concept:
    if concept_id is not None:
        concept = view.concepts.get(concept_id)
        if concept is None or concept.dying_at is not None:
            raise not_found("concept")
        return concept
    if company_id is None or company_id not in view.companies:
        raise not_found("company")
    concept = view.find_label(company_id, label or "")
    if concept is None:
        raise not_found(f"concept {label!r}")
    return concept


def _relation_kind(action: str) -> RelationKind:
    if action == ISA_ACTION:
        return RelationKind.ISA
    if action == SAME_ACTION:
        return RelationKind.SAME
    return RelationKind.REL
