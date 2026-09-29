"""The approval state machine: approve, second-approve, reject with cascade, and the bulk runs.

Every decision is one transaction: the state change, the ontology apply, the domain product
revision bump, the audit entry and the outbox rows commit together or not at all.

Decisions of one tenant never interleave with each other or with proposal creation. Each one
first takes the tenant's decision lock, then row-locks the proposals it decides and re-reads
their state under the lock, so of two concurrent decisions on one proposal exactly one wins and
the other answers `409 proposal_decided`. A lock that is not granted in time answers
`503 busy`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import BulkResult, DecisionResult
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import ProposalState, ProposalType
from app.models.storage.proposal import Proposal
from app.repositories import (
    concept_repository,
    domain_product_repository,
    proposal_approval_repository,
    proposal_repository,
    relation_repository,
)
from app.services import audit_service, decision_lock_service, outbox_service
from app.services.decision_event_service import emit_proposal_event
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_apply_service import apply, delete_removed_company
from app.services.rejection_service import OPEN_STATES, reject_one
from app.utilities.artefact_visibility import readable_artefacts, readable_proposal
from app.utilities.clock import get_clock
from app.utilities.permissions import (
    Scope,
    can_approve,
    can_read_proposal,
    holds_approving_role,
)
from app.utilities.problems import conflict, forbidden, not_found
from app.utilities.proposal_relations import own_relation_ids
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

SECOND_APPROVAL_WHY = "1 of 2 approvals · a Governor must approve too"
APPROVE_ALL_CAPTION = "All pending proposals are now part of the model."
REJECT_ALL_CAPTION = "All pending proposals were discarded."
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
    return _result(caller, view, proposal, outcome, proposals)


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
    return _result(caller, view, proposal, outcome, proposals)


async def reject(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, reason: str | None
) -> DecisionResult:
    proposal = await _load_decidable(session, caller, proposal_id)
    proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    _ensure_can_approve(caller, view, proposal, "reject")
    outcome = await reject_one(session, caller, view, proposal, proposals, reason, False)
    return _result(caller, view, proposal, outcome, proposals)


async def approve_all(session: AsyncSession, caller: Caller) -> BulkResult:
    """Approve every ready proposal the caller may approve, round after round, at most 200."""
    _ensure_holds_approving_role(caller)
    proposals = await _lock_open(session, caller)
    view = await load_view(session, caller.tenant_id, proposals)
    approved, rounds = await _approve_rounds(session, caller, view, proposals)
    remaining = sum(1 for p in proposals if p.state in OPEN_STATES)
    return BulkResult(
        approved=approved,
        rejected=0,
        rounds=rounds,
        remaining=remaining,
        caption=APPROVE_ALL_CAPTION,
    )


async def reject_all(session: AsyncSession, caller: Caller) -> BulkResult:
    """Reject every open proposal the caller may reject; the others are counted in `remaining`."""
    _ensure_holds_approving_role(caller, "reject")
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


async def approve_ready(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposals: list[Proposal],
    candidate_ids: set[uuid.UUID],
    limit: int,
) -> int:
    """Approve, parents first and round after round, the candidates that are open, ready and
    within the caller's approval scope, until `limit` are approved; returns how many were.

    The caller holds the tenant decision lock and `proposals` are the open proposals it locked.
    A candidate that needs a second approver is left for a single decision.
    """
    approved = 0
    progressed = True
    while progressed and approved < limit:
        progressed = False
        for proposal in list(proposals):
            if approved >= limit:
                break
            if proposal.id not in candidate_ids or proposal.state is not ProposalState.PENDING:
                continue
            if not may_approve(caller, view, proposal) or _needs_second_approval(view, proposal):
                continue
            if not view.readiness(proposal)[0]:
                continue
            await _complete_approval(session, caller, view, proposal, proposals, 1, True)
            approved += 1
            progressed = True
    return approved


def may_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> bool:
    """The caller may approve the proposal alone: an approving role in its scope."""
    return _may_approve(caller, view, proposal)


async def _load_decidable(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID
) -> Proposal:
    """Lock the tenant's decisions and the proposal row, then check its state under the lock."""
    await decision_lock_service.acquire(session, caller.tenant_id)
    proposal = await proposal_repository.get_for_update(session, caller.tenant_id, proposal_id)
    if proposal is None:
        raise not_found("proposal")
    if proposal.state not in OPEN_STATES:
        raise conflict("proposal_decided", f"the proposal is already {proposal.state.value}")
    return proposal


async def _lock_open(session: AsyncSession, caller: Caller) -> list[Proposal]:
    await decision_lock_service.acquire(session, caller.tenant_id)
    return await proposal_repository.lock_open(session, caller.tenant_id)


def _scope_of(view: OntologyView, proposal: Proposal) -> Scope:
    """The proposal's domain product, else its company, else the tenant (cross-company)."""
    product = (
        view.domain_products.get(proposal.domain_product_id) if proposal.domain_product_id else None
    )
    return Scope(proposal.company_id, product.template_key if product else None)


def _may_approve(caller: Caller, view: OntologyView, proposal: Proposal) -> bool:
    return can_approve(caller.grants, _scope_of(view, proposal))


def _ensure_can_approve(
    caller: Caller, view: OntologyView, proposal: Proposal, verb: str = "approve"
) -> None:
    if not holds_approving_role(caller.grants):
        raise forbidden(f"Only a Governor or Owner can {verb}")
    if not _may_approve(caller, view, proposal):
        raise forbidden(f"Your roles do not let you {verb} proposals in this scope")


def _ensure_holds_approving_role(caller: Caller, verb: str = "approve") -> None:
    if not holds_approving_role(caller.grants):
        raise forbidden(f"Only a Governor or Owner can {verb}")


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
        company_ids=proposal_company_ids(proposal),
        domain_key=view.proposal_domain_key(proposal),
        origin=proposal.origin,
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
        raise conflict("same_approver", "The same person cannot give both approvals")
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
            company_ids=[product.company_id],
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
        company_ids=proposal_company_ids(proposal),
        domain_key=view.proposal_domain_key(proposal),
        origin=proposal.origin,
    )
    await emit_proposal_event(session, caller, view, proposal, "proposal.approved", outcome, bulk)
    await delete_removed_company(session, caller, view, outcome)
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


def _result(
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    outcome: DecisionOutcome,
    open_proposals: list[Proposal],
) -> DecisionResult:
    """The response: unreadable cascaded proposals and unreadable artefact rows are left out."""
    readable = {
        p.id for p in open_proposals if can_read_proposal(caller.grants, proposal_company_ids(p))
    }
    artefacts = readable_artefacts(caller.grants, outcome.artefacts)
    return DecisionResult(
        proposal=view.proposal_dto(proposal, artefacts),
        artefacts=artefacts,
        cascaded=[
            readable_proposal(caller.grants, c) for c in outcome.cascaded if c.id in readable
        ],
        audit=outcome.audit,
        caption=outcome.caption,
    )
