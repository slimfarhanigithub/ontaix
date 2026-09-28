"""Applies an approved proposal to the ontology; a change proposal alters or removes live rows."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import Artefacts
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import ChangeKind, ProposalType
from app.models.storage.proposal import Proposal
from app.repositories import (
    company_repository,
    concept_repository,
    proposal_repository,
    relation_repository,
)
from app.services import outbox_service
from app.services.concept_removal_service import remove_concepts
from app.services.ontology_view_service import OntologyView
from app.services.rejection_service import OPEN_STATES, reject_one, touches_any
from app.utilities.clock import get_clock
from app.utilities.problems import conflict
from app.utilities.proposal_relations import touched_relation_ids

logger = logging.getLogger(__name__)


async def apply(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    """Type-specific apply; the artefacts snapshot is taken before any row is deleted."""
    if proposal.type is not ProposalType.CHANGE:
        return DecisionOutcome(artefacts=view.proposal_artefacts(proposal))
    match proposal.change_kind:
        case ChangeKind.RENAME:
            return await _apply_rename(session, caller, view, proposal, bulk)
        case ChangeKind.DELETE_CONCEPT:
            return await _apply_delete_concept(
                session, caller, view, proposal, open_proposals, bulk
            )
        case ChangeKind.EDIT_RELATION:
            return await _apply_edit_relation(session, caller, view, proposal, bulk)
        case ChangeKind.REMOVE_RELATION:
            return await _apply_remove_relation(
                session, caller, view, proposal, open_proposals, bulk
            )
        case ChangeKind.REMOVE_COMPANY:
            return await _apply_remove_company(
                session, caller, view, proposal, open_proposals, bulk
            )
        case _:
            return DecisionOutcome(artefacts=Artefacts())


async def _apply_rename(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> DecisionOutcome:
    concept = view.concepts.get(uuid.UUID(proposal.payload["conceptId"]))
    if concept is None:
        raise conflict("proposal_not_ready", "the concept no longer exists")
    new_label = str(proposal.payload["newLabel"])
    existing = view.find_label(concept.company_id, new_label)
    if existing is not None and existing.id != concept.id:
        raise conflict("duplicate_label", f"{new_label} already exists in this company")
    await concept_repository.rename(session, concept, new_label)
    dto = view.concept_dto(concept)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "concept.changed",
        {
            "concept": dto.model_dump(mode="json", by_alias=True),
            "fields": ["label"],
            "proposalId": str(proposal.id),
        },
        company_id=concept.company_id,
        bulk=bulk,
    )
    return DecisionOutcome(artefacts=Artefacts(concepts=[dto]))


async def _apply_delete_concept(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    concept = view.concepts.get(uuid.UUID(proposal.payload["conceptId"]))
    if concept is None:
        raise conflict("proposal_not_ready", "the concept no longer exists")
    doomed = [concept, *view.descendants_of(concept.id)]
    outcome = DecisionOutcome(artefacts=Artefacts())
    for q in list(open_proposals):
        if q.id != proposal.id and q.state in OPEN_STATES and touches_any(view, q, doomed):
            cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
            outcome.cascaded.extend(cascaded.cascaded)
    await remove_concepts(session, caller, view, proposal, doomed, outcome, bulk)
    return outcome


async def _apply_edit_relation(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> DecisionOutcome:
    relation = view.relations.get(uuid.UUID(proposal.payload["relationId"]))
    if relation is None:
        raise conflict("proposal_not_ready", "the relation no longer exists")
    fields: list[str] = []
    action = str(proposal.payload.get("action") or relation.label)
    if action != relation.label:
        fields.append("label")
    a_id, b_id = relation.a_id, relation.b_id
    if proposal.payload.get("reverse"):
        a_id, b_id = b_id, a_id
        fields.append("direction")
    await relation_repository.update(session, relation, label=action, a_id=a_id, b_id=b_id)
    dto = view.relation_dto(relation)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "relation.changed",
        {
            "relation": dto.model_dump(mode="json", by_alias=True),
            "fields": fields,
            "proposalId": str(proposal.id),
        },
        company_id=proposal.company_id,
        bulk=bulk,
    )
    return DecisionOutcome(artefacts=Artefacts(relations=[dto]))


async def _apply_remove_relation(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    relation = view.relations.get(uuid.UUID(proposal.payload["relationId"]))
    if relation is None:
        raise conflict("proposal_not_ready", "the relation no longer exists")
    outcome = DecisionOutcome(artefacts=Artefacts())
    for q in list(open_proposals):
        if (
            q.id != proposal.id
            and q.state in OPEN_STATES
            and relation.id in touched_relation_ids(q)
        ):
            cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
    await relation_repository.mark_dying(session, relation, get_clock().now())
    outcome.artefacts.relations.append(view.relation_dto(relation))
    await relation_repository.delete(session, relation)
    view.forget_relation(relation.id)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "relation.removed",
        {"relationId": str(relation.id), "dying": True, "proposalId": str(proposal.id)},
        company_id=proposal.company_id,
        bulk=bulk,
    )
    return outcome


async def _apply_remove_company(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    company = view.companies.get(uuid.UUID(proposal.payload["companyId"]))
    if company is None:
        raise conflict("proposal_not_ready", "the company no longer exists")
    outcome = DecisionOutcome(artefacts=Artefacts())
    company_concepts = [c for c in view.concepts.values() if c.company_id == company.id]
    for q in list(open_proposals):
        if q.id == proposal.id or q.state not in OPEN_STATES:
            continue
        if q.company_id == company.id or touches_any(view, q, company_concepts):
            cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
    await company_repository.mark_dying(session, company, get_clock().now())
    outcome.artefacts.companies.append(
        view.company_dto(company).model_dump(mode="json", by_alias=True)
    )
    concept_ids = [c.id for c in company_concepts]
    await proposal_repository.detach_company(session, caller.tenant_id, company.id)
    await company_repository.delete(session, company)
    view.forget_company(company.id)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "company.removed",
        {
            "companyId": str(company.id),
            "conceptIds": [str(i) for i in concept_ids],
            "sourceIds": [],
            "proposalId": str(proposal.id),
        },
        bulk=bulk,
    )
    return outcome
