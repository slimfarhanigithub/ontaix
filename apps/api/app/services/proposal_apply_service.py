"""Applies an approved proposal to the ontology; a change proposal alters or removes live rows."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import Artefacts
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import ChangeKind, ProposalType
from app.models.storage.company import Company
from app.models.storage.proposal import Proposal
from app.repositories import (
    company_repository,
    concept_repository,
    document_extraction_job_repository,
    document_import_repository,
    proposal_repository,
    relation_repository,
)
from app.services import (
    attribute_proposal_service,
    deletion_change_service,
    domain_change_service,
    outbox_service,
)
from app.services.concept_removal_service import remove_concepts
from app.services.ontology_view_service import OntologyView
from app.services.rejection_service import OPEN_STATES, reject_one, touches_any
from app.utilities.clock import get_clock
from app.utilities.problems import conflict
from app.utilities.proposal_relations import touched_relation_ids
from app.utilities.proposal_scope import proposal_company_ids

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
    if proposal.type is ProposalType.ATTR:
        await attribute_proposal_service.approve(session, view, caller, proposal, bulk)
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
        case ChangeKind.CREATE_DOMAIN | ChangeKind.EDIT_DOMAIN | ChangeKind.MOVE_CONCEPT_DOMAIN:
            return await domain_change_service.apply(
                session, caller, view, proposal, open_proposals, bulk
            )
        case ChangeKind.DELETE_DOMAIN | ChangeKind.DELETE_BULK:
            return await deletion_change_service.apply(
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
        company_ids=[concept.company_id],
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
            outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
            outcome.absorb_cascade(cascaded)
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
        company_ids=dto.company_ids,
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
            outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
    relation_company_ids = view.relation_dto(relation).company_ids
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
        company_ids=relation_company_ids,
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
            outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
            outcome.absorb_cascade(cascaded)
    await _remove_cross_company_relations(session, caller, view, proposal, company, outcome, bulk)
    await company_repository.mark_dying(session, company, get_clock().now())
    outcome.artefacts.companies.append(
        view.company_dto(company).model_dump(mode="json", by_alias=True)
    )
    concept_ids = [c.id for c in company_concepts]
    outcome.removed_company = company
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
        company_ids=[company.id],
        bulk=bulk,
    )
    return outcome


async def _remove_cross_company_relations(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    company: Company,
    outcome: DecisionOutcome,
    bulk: bool,
) -> None:
    """Every live relation and equivalence between the company and another one leaves with its
    own `relation.removed` event, so the other company's canvas drops the line."""
    now = get_clock().now()
    for relation in view.live_relations():
        a, b = view.concepts.get(relation.a_id), view.concepts.get(relation.b_id)
        if a is None or b is None or a.company_id == b.company_id:
            continue
        if company.id not in (a.company_id, b.company_id):
            continue
        dto = view.relation_dto(relation)
        await relation_repository.mark_dying(session, relation, now)
        outcome.artefacts.relations.append(view.relation_dto(relation))
        await relation_repository.delete(session, relation)
        view.forget_relation(relation.id)
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "relation.removed",
            {"relationId": str(relation.id), "dying": True, "proposalId": str(proposal.id)},
            company_ids=dto.company_ids,
            bulk=bulk,
        )


async def delete_removed_company(
    session: AsyncSession, caller: Caller, view: OntologyView, outcome: DecisionOutcome
) -> None:
    """Delete the company a decision marked dying, once its audit entry and events are written.

    The company's proposals keep their history: their company column is cleared first. The
    company row's foreign keys cascade to its domain products, concepts (with their relations,
    attributes, bindings and expansions), sources, extraction jobs, ontology imports and teach
    session turns; the document imports its extraction jobs read are deleted here, since an
    import belongs to no company.
    """
    company = outcome.removed_company
    if company is None:
        return
    await proposal_repository.detach_company(session, caller.tenant_id, company.id)
    import_ids = await document_extraction_job_repository.import_ids_for_company(
        session, caller.tenant_id, company.id
    )
    await document_import_repository.delete_many(session, caller.tenant_id, import_ids)
    await company_repository.delete(session, company)
    view.forget_company(company.id)
