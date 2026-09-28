"""The approval state machine: approve, second-approve, reject with cascade, and the bulk runs.

Every decision is one transaction: the state change, the ontology apply, the domain product
revision bump, the audit entry and the outbox rows commit together or not at all.

Decisions of one tenant never interleave. Each one first takes the tenant's decision lock, then
row-locks the proposals it decides and re-reads their state under the lock, so of two concurrent
decisions on one proposal exactly one wins and the other answers `409 proposal_decided`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import BulkResult, DecisionResult, FinaliseResult
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import NodeKind, ProposalState, ProposalType, RelationKind
from app.models.storage.proposal import Proposal
from app.repositories import (
    concept_repository,
    domain_product_repository,
    proposal_approval_repository,
    proposal_repository,
    relation_repository,
)
from app.services import audit_service, outbox_service
from app.services.decision_event_service import emit_finalised, emit_proposal_event
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_apply_service import apply
from app.services.rejection_service import OPEN_STATES, reject_one
from app.utilities.clock import get_clock
from app.utilities.permissions import Scope, can_approve, can_finalise, holds_approving_role
from app.utilities.problems import conflict, forbidden, not_found
from app.utilities.proposal_relations import own_relation_ids

logger = logging.getLogger(__name__)

SECOND_APPROVAL_WHY = "1 of 2 approvals · a Governor must approve too"
APPROVE_ALL_CAPTION = "All pending proposals are now part of the model."
REJECT_ALL_CAPTION = "All pending proposals were discarded."
FINALISE_AUDIT_WHAT = "finalised all scenes"
MAX_BULK_ROUNDS = 200


async def approve(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, *, bulk: bool = False
) -> DecisionResult:
    """Approve a proposal; on a half-approved change this completes the second approval."""
    proposal = await _load_decidable(session, caller, proposal_id)
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
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
    proposal = await _load_decidable(session, caller, proposal_id)
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
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
    proposal = await _load_decidable(session, caller, proposal_id)
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    _ensure_can_approve(caller, view, proposal)
    outcome = await reject_one(session, caller, view, proposal, proposals, reason, False)
    return _result(view, proposal, outcome)


async def approve_all(session: AsyncSession, caller: Caller) -> BulkResult:
    """Approve every ready proposal the caller may approve, round after round, at most 200."""
    _ensure_holds_approving_role(caller)
    proposals = await _lock_open(session, caller)
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
    await emit_finalised(session, caller, view, result)
    return result


async def reject_all(session: AsyncSession, caller: Caller) -> BulkResult:
    """Reject every open proposal the caller may reject; the others are counted in `remaining`."""
    _ensure_holds_approving_role(caller)
    proposals = await _lock_open(session, caller)
    view = await load_view(session, caller.tenant_id, proposals)
    rejected = 0
    for proposal in list(proposals):
        if proposal.state not in OPEN_STATES:
            continue
        if not _may_approve(caller, view, proposal):
            continue
        await reject_one(session, caller, view, proposal, proposals, None, True)
        rejected += 1
    remaining = sum(1 for p in proposals if p.state in OPEN_STATES)
    return BulkResult(
        approved=0, rejected=rejected, rounds=1, remaining=remaining, caption=REJECT_ALL_CAPTION
    )


async def finalise_all(session: AsyncSession, caller: Caller) -> FinaliseResult:
    """Approve everything that is ready; with the story layer off no scene is played."""
    if not can_finalise(caller.grants):
        raise forbidden("finalising requires Governor at tenant scope")
    proposals = await _lock_open(session, caller)
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
    await emit_finalised(
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


async def _load_decidable(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID
) -> Proposal:
    """Lock the tenant's decisions and the proposal row, then check its state under the lock."""
    await proposal_repository.lock_decisions(session, caller.tenant_id)
    proposal = await proposal_repository.get_for_update(session, caller.tenant_id, proposal_id)
    if proposal is None:
        raise not_found("proposal")
    if proposal.state not in OPEN_STATES:
        raise conflict("proposal_decided", f"the proposal is already {proposal.state.value}")
    return proposal


async def _lock_open(session: AsyncSession, caller: Caller) -> list[Proposal]:
    await proposal_repository.lock_decisions(session, caller.tenant_id)
    return await proposal_repository.lock_open(session, caller.tenant_id)


def _scope_of(view: OntologyView, proposal: Proposal) -> Scope:
    """The proposal's domain product, else its company, else the tenant (cross-company)."""
    product = (
        view.domain_products.get(proposal.domain_product_id) if proposal.domain_product_id else None
    )
    return Scope(proposal.company_id, product.template_key if product else None)


def _may_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> bool:
    return can_approve(caller.grants, _scope_of(view, proposal))


def _ensure_can_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> None:
    if not _may_approve(caller, view, proposal):
        raise forbidden("your roles do not allow deciding this proposal")


def _ensure_holds_approving_role(caller: Caller) -> None:
    if not holds_approving_role(caller.grants):
        raise forbidden("deciding proposals requires Owner or Governor")


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
) -> DecisionOutcome:
    approval = await proposal_approval_repository.create(
        session, caller.tenant_id, proposal.id, 1, caller.user_id
    )
    view.register_approval(approval)
    why = f"{proposal.why} · {SECOND_APPROVAL_WHY}" if proposal.why else SECOND_APPROVAL_WHY
    await proposal_repository.mark_half_approved(session, proposal, why)
    audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        proposal.type.value,
        f"{proposal.title} · 1 of 2 approvals",
        True,
        proposal.id,
    )
    outcome = DecisionOutcome(artefacts=view.proposal_artefacts(proposal), audit=audit)
    await emit_proposal_event(
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
) -> DecisionOutcome:
    if ordinal == 2 and _first_approver(view, proposal) == caller.user_id:
        raise conflict("same_approver", "the second approver must be a different user")
    approval = await proposal_approval_repository.create(
        session, caller.tenant_id, proposal.id, ordinal, caller.user_id
    )
    view.register_approval(approval)
    await proposal_repository.mark_decided(
        session, proposal, ProposalState.APPROVED, get_clock().now()
    )
    await _clear_pending(session, view, proposal)
    outcome = await apply(session, caller, view, proposal, open_proposals, bulk)
    if proposal.domain_product_id and proposal.domain_product_id in view.domain_products:
        product = view.domain_products[proposal.domain_product_id]
        await domain_product_repository.bump_revision(session, product)
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
    await emit_proposal_event(session, caller, view, proposal, "proposal.approved", outcome, bulk)
    return outcome


async def _clear_pending(session: AsyncSession, view: OntologyView, proposal: Proposal) -> None:
    if proposal.concept_id and proposal.concept_id in view.concepts:
        await concept_repository.clear_pending(session, view.concepts[proposal.concept_id])
    for rid in own_relation_ids(proposal):
        if rid in view.relations:
            await relation_repository.clear_pending(session, view.relations[rid])


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


def _result(view: OntologyView, proposal: Proposal, outcome: DecisionOutcome) -> DecisionResult:
    return DecisionResult(
        proposal=view.proposal_dto(proposal, outcome.artefacts),
        artefacts=outcome.artefacts,
        cascaded=outcome.cascaded,
        audit=outcome.audit,
        caption=outcome.caption,
    )
