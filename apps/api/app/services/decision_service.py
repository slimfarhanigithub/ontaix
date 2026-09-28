"""The approval state machine: approve, second-approve, reject with cascade, and the bulk runs.

Every decision is one transaction: the state change, the ontology apply, the domain product
revision bump, the audit entry and the outbox rows commit together or not at all.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.audit import AuditEntry as AuditEntryDto
from app.models.api.proposal import (
    Artefacts,
    BulkResult,
    DecisionResult,
    FinaliseResult,
)
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.base import (
    ChangeKind,
    NodeKind,
    ProposalState,
    ProposalType,
    RelationKind,
)
from app.models.storage.proposal import Proposal
from app.repositories import (
    company_repository,
    concept_repository,
    proposal_approval_repository,
    proposal_repository,
    relation_repository,
)
from app.services import audit_service, outbox_service
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities.clock import get_clock
from app.utilities.permissions import Scope, can_approve, can_finalise
from app.utilities.problems import conflict, forbidden, not_found

logger = logging.getLogger(__name__)

SECOND_APPROVAL_WHY = "1 of 2 approvals · a Governor must approve too"
REJECTED_CAPTION = "{title} was not kept. The model only holds what its owners approved."
APPROVE_ALL_CAPTION = "All pending proposals are now part of the model."
REJECT_ALL_CAPTION = "All pending proposals were discarded."
FINALISE_AUDIT_WHAT = "finalised all scenes"
MAX_BULK_ROUNDS = 200
OPEN_STATES = frozenset({ProposalState.PENDING, ProposalState.HALF_APPROVED})


@dataclass
class _Outcome:
    artefacts: Artefacts
    cascaded: list[ProposalDto] = field(default_factory=list)
    caption: str | None = None
    audit: AuditEntryDto | None = None


# ---------------------------------------------------------------------------- public


async def approve(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, *, bulk: bool = False
) -> DecisionResult:
    """Approve a proposal; on a half-approved change this completes the second approval."""
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    proposal = await _load_decidable(session, caller, proposal_id)
    _ensure_can_approve(caller, view, proposal)
    ready, wait_for = view.readiness(proposal)
    if not ready:
        raise conflict("proposal_not_ready", f"after {wait_for}")
    if proposal.state is ProposalState.HALF_APPROVED:
        outcome = await _complete_approval(session, caller, view, proposal, proposals, 2, bulk)
    elif _needs_second_approval(view, proposal):
        outcome = await _half_approve(session, caller, view, proposal, bulk)
    else:
        outcome = await _complete_approval(session, caller, view, proposal, proposals, 1, bulk)
    return _result(view, proposal, outcome)


async def second_approve(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID
) -> DecisionResult:
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    proposal = await _load_decidable(session, caller, proposal_id)
    if proposal.state is not ProposalState.HALF_APPROVED:
        raise conflict("proposal_not_half_approved", "the proposal has no first approval yet")
    _ensure_can_approve(caller, view, proposal)
    ready, wait_for = view.readiness(proposal)
    if not ready:
        raise conflict("proposal_not_ready", f"after {wait_for}")
    outcome = await _complete_approval(session, caller, view, proposal, proposals, 2, False)
    return _result(view, proposal, outcome)


async def reject(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, reason: str | None
) -> DecisionResult:
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    proposal = await _load_decidable(session, caller, proposal_id)
    _ensure_can_approve(caller, view, proposal)
    outcome = await _reject_one(session, caller, view, proposal, proposals, reason, False)
    return _result(view, proposal, outcome)


async def approve_all(session: AsyncSession, caller: Caller) -> BulkResult:
    """Approve every ready proposal the caller may approve, round after round, at most 200."""
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    approved, rounds = await _approve_rounds(session, caller, view, proposals)
    remaining = sum(1 for p in proposals if p.state in OPEN_STATES)
    result = BulkResult(
        approved=approved,
        rejected=0,
        rounds=rounds,
        remaining=remaining,
        caption=APPROVE_ALL_CAPTION,
    )
    await _emit_finalised(session, caller, view, result)
    return result


async def reject_all(session: AsyncSession, caller: Caller) -> BulkResult:
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    rejected = 0
    for proposal in list(proposals):
        if proposal.state not in OPEN_STATES:
            continue
        if not _may_approve(caller, view, proposal):
            continue
        await _reject_one(session, caller, view, proposal, proposals, None, True)
        rejected += 1
    remaining = sum(1 for p in proposals if p.state in OPEN_STATES)
    return BulkResult(
        approved=0, rejected=rejected, rounds=1, remaining=remaining, caption=REJECT_ALL_CAPTION
    )


async def finalise_all(session: AsyncSession, caller: Caller) -> FinaliseResult:
    """Approve everything that is ready; with the story layer off no scene is played."""
    if not can_finalise(caller.grants):
        raise forbidden("finalising requires Governor at tenant scope")
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    approved, rounds = await _approve_rounds(session, caller, view, proposals)
    companies = len(view.companies)
    concepts = sum(1 for c in view.live_concepts() if c.kind is NodeKind.CONCEPT)
    equivalences = sum(1 for r in view.live_relations() if r.kind is RelationKind.SAME)
    plural = "y" if companies == 1 else "ies"
    caption = (
        f"{companies} compan{plural}, {concepts} concepts, 0 bound to data, "
        f"{equivalences} equivalences. Everything approved."
    )
    await audit_service.record(
        session, caller.tenant_id, caller.actor, "demo", FINALISE_AUDIT_WHAT, True
    )
    remaining = sum(1 for p in proposals if p.state in OPEN_STATES)
    await _emit_finalised(
        session,
        caller,
        view,
        BulkResult(
            approved=approved, rejected=0, rounds=rounds, remaining=remaining, caption=caption
        ),
    )
    return FinaliseResult(
        companies=companies,
        concepts=concepts,
        bound=0,
        equivalences=equivalences,
        approved=approved,
        scenes_played=0,
        caption=caption,
    )


# ---------------------------------------------------------------------------- approval


async def _load_decidable(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID
) -> Proposal:
    proposal = await proposal_repository.get(session, caller.tenant_id, proposal_id)
    if proposal is None:
        raise not_found("proposal")
    if proposal.state not in OPEN_STATES:
        raise conflict("proposal_decided", f"the proposal is already {proposal.state.value}")
    return proposal


def _scope_of(view: OntologyView, proposal: Proposal) -> Scope:
    product = (
        view.domain_products.get(proposal.domain_product_id) if proposal.domain_product_id else None
    )
    return Scope(proposal.company_id, product.template_key if product else None)


def _may_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> bool:
    return can_approve(caller.grants, _scope_of(view, proposal))


def _ensure_can_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> None:
    if not _may_approve(caller, view, proposal):
        raise forbidden("your roles do not allow deciding this proposal")


def _needs_second_approval(view: OntologyView, proposal: Proposal) -> bool:
    return bool(
        view.settings
        and view.settings.two_approvers
        and proposal.type is ProposalType.CHANGE
        and proposal.state is ProposalState.PENDING
    )


def _first_approver(view: OntologyView, proposal: Proposal) -> uuid.UUID | None:
    approvals = view.approvals.get(proposal.id, [])
    return approvals[0].user_id if approvals else None


async def _half_approve(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> _Outcome:
    approval = await proposal_approval_repository.create(
        session, caller.tenant_id, proposal.id, 1, caller.user_id
    )
    view.register_approval(approval)
    proposal.state = ProposalState.HALF_APPROVED
    proposal.why = (
        f"{proposal.why} · {SECOND_APPROVAL_WHY}" if proposal.why else SECOND_APPROVAL_WHY
    )
    await session.flush()
    audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        proposal.type.value,
        f"{proposal.title} · 1 of 2 approvals",
        True,
        proposal.id,
    )
    outcome = _Outcome(artefacts=view.proposal_artefacts(proposal), audit=audit)
    await _emit_proposal_event(
        session, caller, view, proposal, "proposal.half_approved", outcome, bulk
    )
    return outcome


async def _complete_approval(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    ordinal: int,
    bulk: bool,
) -> _Outcome:
    if ordinal == 2 and _first_approver(view, proposal) == caller.user_id:
        raise conflict("same_approver", "the second approver must be a different user")
    approval = await proposal_approval_repository.create(
        session, caller.tenant_id, proposal.id, ordinal, caller.user_id
    )
    view.register_approval(approval)
    proposal.state = ProposalState.APPROVED
    proposal.decided_at = get_clock().now()
    _clear_pending(view, proposal)
    outcome = await _apply(session, caller, view, proposal, open_proposals, bulk)
    if proposal.domain_product_id and proposal.domain_product_id in view.domain_products:
        product = view.domain_products[proposal.domain_product_id]
        product.revision += 1
        await session.flush()
        dto = view.domain_product_dto(product)
        outcome.artefacts.domain_products = [dto]
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "domain_product.changed",
            {"domainProduct": dto.model_dump(mode="json", by_alias=True), "fields": ["revision"]},
            company_id=product.company_id,
            bulk=bulk,
        )
    await session.flush()
    outcome.caption = proposal.caption
    outcome.audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        proposal.type.value,
        proposal.title,
        True,
        proposal.id,
    )
    await _emit_proposal_event(session, caller, view, proposal, "proposal.approved", outcome, bulk)
    return outcome


def _clear_pending(view: OntologyView, proposal: Proposal) -> None:
    if proposal.concept_id and proposal.concept_id in view.concepts:
        view.concepts[proposal.concept_id].pending = False
    for rid in [proposal.relation_id, *(proposal.relation_ids or [])]:
        if rid and rid in view.relations:
            view.relations[rid].pending = False


async def _apply(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> _Outcome:
    """Type-specific apply; the artefacts snapshot is taken before any row is deleted."""
    if proposal.type is not ProposalType.CHANGE:
        return _Outcome(artefacts=view.proposal_artefacts(proposal))
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
            return _Outcome(artefacts=Artefacts())


async def _apply_rename(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> _Outcome:
    concept = view.concepts.get(uuid.UUID(proposal.payload["conceptId"]))
    if concept is None:
        raise conflict("proposal_not_ready", "the concept no longer exists")
    new_label = str(proposal.payload["newLabel"])
    existing = view.find_label(concept.company_id, new_label)
    if existing is not None and existing.id != concept.id:
        raise conflict("duplicate_label", f"{new_label} already exists in this company")
    concept.label = new_label
    await session.flush()
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
    return _Outcome(artefacts=Artefacts(concepts=[dto]))


async def _apply_delete_concept(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> _Outcome:
    concept = view.concepts.get(uuid.UUID(proposal.payload["conceptId"]))
    if concept is None:
        raise conflict("proposal_not_ready", "the concept no longer exists")
    doomed = [concept, *view.descendants_of(concept.id)]
    outcome = _Outcome(artefacts=Artefacts())
    for q in list(open_proposals):
        if q.id != proposal.id and q.state in OPEN_STATES and _touches_any(view, q, doomed):
            cascaded = await _reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
            outcome.cascaded.extend(cascaded.cascaded)
    await _remove_concepts(session, caller, view, proposal, doomed, outcome, bulk)
    return outcome


async def _apply_edit_relation(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> _Outcome:
    relation = view.relations.get(uuid.UUID(proposal.payload["relationId"]))
    if relation is None:
        raise conflict("proposal_not_ready", "the relation no longer exists")
    fields: list[str] = []
    action = str(proposal.payload.get("action") or relation.label)
    if action != relation.label:
        relation.label = action
        fields.append("label")
    if proposal.payload.get("reverse"):
        relation.a_id, relation.b_id = relation.b_id, relation.a_id
        fields.append("direction")
    await session.flush()
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
    return _Outcome(artefacts=Artefacts(relations=[dto]))


async def _apply_remove_relation(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> _Outcome:
    relation = view.relations.get(uuid.UUID(proposal.payload["relationId"]))
    if relation is None:
        raise conflict("proposal_not_ready", "the relation no longer exists")
    outcome = _Outcome(artefacts=Artefacts())
    for q in list(open_proposals):
        if q.id != proposal.id and q.state in OPEN_STATES and relation.id in _relation_ids(q):
            cascaded = await _reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
    relation.dying_at = get_clock().now()
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
) -> _Outcome:
    company = view.companies.get(uuid.UUID(proposal.payload["companyId"]))
    if company is None:
        raise conflict("proposal_not_ready", "the company no longer exists")
    outcome = _Outcome(artefacts=Artefacts())
    company_concepts = [c for c in view.concepts.values() if c.company_id == company.id]
    for q in list(open_proposals):
        if q.id == proposal.id or q.state not in OPEN_STATES:
            continue
        if q.company_id == company.id or _touches_any(view, q, company_concepts):
            cascaded = await _reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
    now = get_clock().now()
    company.dying_at = now
    outcome.artefacts.companies.append(
        view.company_dto(company).model_dump(mode="json", by_alias=True)
    )
    concept_ids = [c.id for c in company_concepts]
    # Proposals of the company keep their history: detach them before the cascade deletes rows.
    for q in await proposal_repository.list_for_tenant(session, caller.tenant_id):
        if q.company_id == company.id:
            q.company_id = None
    await session.flush()
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
    proposal.company_id = None
    return outcome


# ---------------------------------------------------------------------------- rejection


async def _reject_one(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    reason: str | None,
    bulk: bool,
) -> _Outcome:
    """Reject one proposal, cascade to dependants, and remove its pending artefacts."""
    proposal.state = ProposalState.REJECTED
    proposal.decided_at = get_clock().now()
    await session.flush()
    outcome = _Outcome(artefacts=view.proposal_artefacts(proposal))
    outcome.audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        proposal.type.value,
        proposal.title,
        False,
        proposal.id,
    )
    concept = view.concepts.get(proposal.concept_id) if proposal.concept_id else None
    if concept is not None:
        for q in list(open_proposals):
            if q.id == proposal.id or q.state not in OPEN_STATES:
                continue
            descends = (
                q.concept_id is not None
                and q.concept_id != concept.id
                and view.descends(q.concept_id, concept.id)
            )
            if descends or _touches_relation(view, q, concept.id):
                cascaded = await _reject_one(session, caller, view, q, open_proposals, None, bulk)
                outcome.cascaded.append(view.proposal_dto(q, cascaded.artefacts))
                outcome.cascaded.extend(cascaded.cascaded)
        concept.pending = False
        await _remove_concepts(session, caller, view, proposal, [concept], outcome, bulk)
    else:
        for rid in _relation_ids(proposal):
            relation = view.relations.get(rid)
            if relation is None:
                continue
            await relation_repository.delete(session, relation)
            view.forget_relation(rid)
            await outbox_service.emit(
                session,
                caller.tenant_id,
                caller.actor,
                "relation.removed",
                {"relationId": str(rid), "dying": False, "proposalId": str(proposal.id)},
                company_id=proposal.company_id,
                bulk=bulk,
            )
    outcome.caption = REJECTED_CAPTION.format(title=proposal.title)
    await _emit_proposal_event(session, caller, view, proposal, "proposal.rejected", outcome, bulk)
    return outcome


async def _remove_concepts(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    doomed: list,
    outcome: _Outcome,
    bulk: bool,
) -> None:
    """Mark the cells dying for the snapshot, then delete them; relations cascade in the DB."""
    doomed = [c for c in doomed if c.id in view.concepts]
    if not doomed:
        return
    now = get_clock().now()
    company_id = doomed[0].company_id
    relation_ids: list[uuid.UUID] = []
    for c in doomed:
        c.dying_at = now
        for r in view.relations_touching(c.id):
            if r.id not in relation_ids:
                relation_ids.append(r.id)
                r.dying_at = now
    outcome.artefacts.concepts = [view.concept_dto(c) for c in doomed]
    outcome.artefacts.relations = [view.relation_dto(view.relations[r]) for r in relation_ids]
    for c in doomed:
        await concept_repository.delete(session, c)
        view.forget_concept(c.id)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "concept.dying",
        {
            "conceptIds": [str(c.id) for c in doomed],
            "relationIds": [str(r) for r in relation_ids],
            "bindingIds": [],
            "proposalId": str(proposal.id),
        },
        company_id=company_id,
        bulk=bulk,
    )


def _relation_ids(proposal: Proposal) -> list[uuid.UUID]:
    ids = list(proposal.relation_ids or [])
    if proposal.relation_id:
        ids.insert(0, proposal.relation_id)
    payload_relation = proposal.payload.get("relationId") if proposal.payload else None
    if payload_relation:
        ids.append(uuid.UUID(str(payload_relation)))
    return ids


def _touches_relation(view: OntologyView, proposal: Proposal, concept_id: uuid.UUID) -> bool:
    for rid in _relation_ids(proposal):
        relation = view.relations.get(rid)
        if relation is not None and concept_id in (relation.a_id, relation.b_id):
            return True
    return False


def _touches_any(view: OntologyView, proposal: Proposal, concepts: list) -> bool:
    ids = {c.id for c in concepts}
    if proposal.concept_id in ids:
        return True
    payload_concept = proposal.payload.get("conceptId") if proposal.payload else None
    if payload_concept and uuid.UUID(str(payload_concept)) in ids:
        return True
    return any(_touches_relation(view, proposal, cid) for cid in ids)


# ---------------------------------------------------------------------------- bulk


async def _approve_rounds(
    session: AsyncSession, caller: Caller, view: OntologyView, proposals: list[Proposal]
) -> tuple[int, int]:
    approved = rounds = 0
    while rounds < MAX_BULK_ROUNDS:
        progressed = False
        for proposal in list(proposals):
            if proposal.state not in OPEN_STATES or not _may_approve(caller, view, proposal):
                continue
            if not view.readiness(proposal)[0]:
                continue
            if proposal.state is ProposalState.HALF_APPROVED:
                if _first_approver(view, proposal) == caller.user_id:
                    continue
                await _complete_approval(session, caller, view, proposal, proposals, 2, True)
            elif _needs_second_approval(view, proposal):
                await _half_approve(session, caller, view, proposal, True)
                continue
            else:
                await _complete_approval(session, caller, view, proposal, proposals, 1, True)
            approved += 1
            progressed = True
        rounds += 1
        if not progressed:
            break
    return approved, rounds


async def _emit_finalised(
    session: AsyncSession, caller: Caller, view: OntologyView, result: BulkResult
) -> None:
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "proposal.finalised",
        {
            "approved": result.approved,
            "rejected": result.rejected,
            "rounds": result.rounds,
            "remaining": result.remaining,
            "companies": len(view.companies),
            "concepts": sum(1 for c in view.live_concepts() if c.kind is NodeKind.CONCEPT),
            "bound": 0,
            "equivalences": sum(1 for r in view.live_relations() if r.kind is RelationKind.SAME),
            "caption": result.caption,
        },
        bulk=True,
    )


# ---------------------------------------------------------------------------- results


async def _emit_proposal_event(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    event_type: str,
    outcome: _Outcome,
    bulk: bool,
) -> None:
    dto = view.proposal_dto(proposal)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        event_type,
        {
            "proposal": dto.model_dump(mode="json", by_alias=True, exclude={"artefacts"}),
            "artefacts": outcome.artefacts.model_dump(mode="json", by_alias=True),
            "cascaded": [
                c.model_dump(mode="json", by_alias=True, exclude={"artefacts"})
                for c in outcome.cascaded
            ],
            "caption": outcome.caption,
        },
        company_id=proposal.company_id if proposal.company_id in view.companies else None,
        bulk=bulk,
    )


def _result(view: OntologyView, proposal: Proposal, outcome: _Outcome) -> DecisionResult:
    return DecisionResult(
        proposal=view.proposal_dto(proposal, outcome.artefacts),
        artefacts=outcome.artefacts,
        cascaded=outcome.cascaded,
        audit=outcome.audit,
        caption=outcome.caption,
    )
