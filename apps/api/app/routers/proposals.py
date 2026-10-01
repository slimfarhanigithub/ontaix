"""Proposals: list, create, batch, decisions, branch approval and the bulk runs."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, Request, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.deletion_impact import DeletionImpact, DeletionTarget
from app.models.api.drafts import ProposalBatch, ProposalDraft
from app.models.api.page import PageOf
from app.models.api.proposal import (
    BranchResult,
    BulkDeleteRequest,
    BulkResult,
    DecisionResult,
    Proposal,
    ProposalEdit,
    RejectRequest,
)
from app.services import (
    branch_approval_service,
    decision_service,
    deletion_impact_service,
    proposal_edit_service,
    proposal_read_service,
)
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Proposals"])


@router.get("/proposals", response_model=PageOf[Proposal])
async def list_proposals(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> PageOf[Proposal]:
    query = parse_list_query(
        request.query_params, proposal_read_service.FILTERABLE, proposal_read_service.SORTABLE
    )
    return await proposal_read_service.list_proposals(session, caller, query)


@router.post("/proposals", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
async def create_proposal(
    draft: ProposalDraft, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await proposal_read_service.create_proposal(session, caller, draft)


@router.post(
    "/proposals/batch", response_model=list[Proposal], status_code=status.HTTP_202_ACCEPTED
)
async def create_proposal_batch(
    body: ProposalBatch, session: SessionDependency, caller: CallerDependency
) -> list[Proposal]:
    return await proposal_read_service.create_batch(session, caller, body)


@router.post("/proposals/approve-all", response_model=BulkResult)
async def approve_all(session: SessionDependency, caller: CallerDependency) -> BulkResult:
    return await decision_service.approve_all(session, caller)


@router.post("/proposals/reject-all", response_model=BulkResult)
async def reject_all(session: SessionDependency, caller: CallerDependency) -> BulkResult:
    return await decision_service.reject_all(session, caller)


@router.post(
    "/proposals/bulk-delete", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_bulk_delete(
    body: BulkDeleteRequest, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await proposal_read_service.propose_bulk_delete(session, caller, body)


@router.post("/deletion-impact", response_model=DeletionImpact)
async def get_deletion_impact(
    body: DeletionTarget, session: SessionDependency, caller: CallerDependency
) -> DeletionImpact:
    return await deletion_impact_service.impact_for(session, caller, body)


@router.get("/proposals/{proposal_id}", response_model=Proposal)
async def get_proposal(
    proposal_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await proposal_read_service.get_proposal(session, caller, proposal_id)


@router.patch("/proposals/{proposal_id}", response_model=Proposal)
async def edit_pending_proposal(
    proposal_id: uuid.UUID,
    body: ProposalEdit,
    session: SessionDependency,
    caller: CallerDependency,
) -> Proposal:
    return await proposal_edit_service.edit_proposal(session, caller, proposal_id, body)


@router.post("/proposals/{proposal_id}/approve", response_model=DecisionResult)
async def approve_proposal(
    proposal_id: uuid.UUID,
    session: SessionDependency,
    caller: CallerDependency,
    expectedRevision: int | None = Query(default=None, ge=0),  # noqa: N803 - contract name
) -> DecisionResult:
    return await decision_service.approve(
        session, caller, proposal_id, expected_revision=expectedRevision
    )


@router.post("/proposals/{proposal_id}/approve-branch", response_model=BranchResult)
async def approve_proposal_branch(proposal_id: uuid.UUID, caller: CallerDependency) -> BranchResult:
    return await branch_approval_service.approve_branch(caller, proposal_id)


@router.post("/proposals/{proposal_id}/second-approve", response_model=DecisionResult)
async def second_approve_proposal(
    proposal_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> DecisionResult:
    return await decision_service.second_approve(session, caller, proposal_id)


@router.post("/proposals/{proposal_id}/reject", response_model=DecisionResult)
async def reject_proposal(
    proposal_id: uuid.UUID,
    session: SessionDependency,
    caller: CallerDependency,
    body: RejectRequest | None = None,
) -> DecisionResult:
    return await decision_service.reject(
        session, caller, proposal_id, body.reason if body else None
    )
