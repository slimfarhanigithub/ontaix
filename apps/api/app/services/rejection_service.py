"""Rejecting one proposal: its own pending artefacts leave, and dependants are rejected too.

A rejection only ever removes what the rejected proposal created while pending. A change proposal
points at a live row it would have changed; that row is its target, not its artefact, and stays.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import ProposalState
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import concept_repository, proposal_repository, relation_repository
from app.services import attribute_proposal_service, audit_service, outbox_service
from app.services.concept_removal_service import remove_concepts
from app.services.decision_event_service import emit_proposal_event
from app.services.ontology_view_service import OntologyView
from app.utilities.clock import get_clock
from app.utilities.proposal_relations import own_relation_ids, touched_relation_ids
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

REJECTED_CAPTION = "{title} was not kept. The model only holds what its owners approved."
OPEN_STATES = frozenset({ProposalState.PENDING, ProposalState.HALF_APPROVED})


async def reject_one(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    reason: str | None,
    bulk: bool,
) -> DecisionOutcome:
    """Reject one proposal, cascade to dependants, and remove its own pending artefacts."""
    await proposal_repository.mark_decided(
        session, proposal, ProposalState.REJECTED, get_clock().now()
    )
    outcome = DecisionOutcome(artefacts=view.proposal_artefacts(proposal))
    outcome.audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        proposal.type.value,
        proposal.title,
        False,
        proposal.id,
        company_ids=proposal_company_ids(proposal),
        domain_key=view.proposal_domain_key(proposal),
        origin=proposal.origin,
    )
    concept = view.concepts.get(proposal.concept_id) if proposal.concept_id else None
    if concept is not None and concept.pending:
        for q in list(open_proposals):
            if q.id == proposal.id or q.state not in OPEN_STATES:
                continue
            descends = (
                q.concept_id is not None
                and q.concept_id != concept.id
                and view.descends(q.concept_id, concept.id)
            )
            touches = _touches_relation(view, q, concept.id) or _touches_attribute(
                view, q, concept.id
            )
            if descends or touches:
                cascaded = await reject_one(session, caller, view, q, open_proposals, None, bulk)
                outcome.add_cascaded(
                    view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q)
                )
                outcome.absorb_cascade(cascaded)
        await concept_repository.clear_pending(session, concept)
        await remove_concepts(session, caller, view, proposal, [concept], outcome, bulk)
    else:
        await attribute_proposal_service.remove(session, view, caller, proposal, bulk)
        for rid in own_relation_ids(proposal):
            relation = view.relations.get(rid)
            if relation is None or not relation.pending:
                continue
            relation_company_ids = view.relation_dto(relation).company_ids
            await relation_repository.delete(session, relation)
            view.forget_relation(rid)
            await outbox_service.emit(
                session,
                caller.tenant_id,
                caller.actor,
                "relation.removed",
                {"relationId": str(rid), "dying": False, "proposalId": str(proposal.id)},
                company_ids=relation_company_ids,
                bulk=bulk,
            )
    outcome.caption = REJECTED_CAPTION.format(title=proposal.title)
    await emit_proposal_event(session, caller, view, proposal, "proposal.rejected", outcome, bulk)
    return outcome


def touches_any(view: OntologyView, proposal: Proposal, concepts: list[Concept]) -> bool:
    """True when the proposal creates, targets, relates or describes any of `concepts`."""
    ids = {c.id for c in concepts}
    if proposal.concept_id in ids:
        return True
    payload = proposal.payload or {}
    targets = [payload["conceptId"]] if payload.get("conceptId") else []
    targets.extend(payload.get("conceptIds") or [])
    if any(uuid.UUID(str(target)) in ids for target in targets):
        return True
    if any(_touches_attribute(view, proposal, cid) for cid in ids):
        return True
    return any(_touches_relation(view, proposal, cid) for cid in ids)


def _touches_attribute(view: OntologyView, proposal: Proposal, concept_id: uuid.UUID) -> bool:
    """True when the proposal's attribute belongs to the concept."""
    attribute = view.attribute(proposal.attribute_id)
    return attribute is not None and attribute.concept_id == concept_id


def _touches_relation(view: OntologyView, proposal: Proposal, concept_id: uuid.UUID) -> bool:
    for rid in touched_relation_ids(proposal):
        relation = view.relations.get(rid)
        if relation is not None and concept_id in (relation.a_id, relation.b_id):
            return True
    return False
