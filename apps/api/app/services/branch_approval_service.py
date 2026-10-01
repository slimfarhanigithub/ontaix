"""`POST /proposals/{proposalId}/approve-branch`: a proposed concept and its branch, in batches.

The root must be a `concept` or `spec` proposal the caller may approve, open or approved by an
earlier call on the same root; a rejected root is refused. Each batch is its
own short transaction: it takes the tenant decision lock, re-reads the open proposals and the
branch under that lock, approves the ready ones the caller may approve alone, parents first, at
most `ONTAIX_BRANCH_APPROVE_BATCH` of them, and commits, so other decisions interleave between
batches and a rejection committed meanwhile is seen. At most `ONTAIX_BRANCH_APPROVE_MAX_ROUNDS`
batches run per call; committed batches stay committed, and `complete` false asks the client to
call again on the same root. A `busy` lock after a committed batch answers the progress so far.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.clients.db_client import tenant_session
from app.config import get_settings
from app.models.api.proposal import BranchResult
from app.models.storage.base import ProposalState
from app.models.storage.proposal import Proposal
from app.repositories import proposal_repository
from app.services import decision_lock_service, decision_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_branch_service import OPEN_STATES, ROOT_TYPES, BranchIndex
from app.utilities.contention import is_contention
from app.utilities.permissions import can_read_proposal, holds_approving_role
from app.utilities.problems import ProblemError, conflict, forbidden, not_found
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Batch:
    approved: int
    skipped: int
    remaining: int
    ready_left: bool


async def approve_branch(caller: Caller, proposal_id: uuid.UUID) -> BranchResult:
    settings = get_settings()
    approved = batches = 0
    last: _Batch | None = None
    for _ in range(settings.branch_approve_max_rounds):
        try:
            async with tenant_session(caller.tenant_id) as session:
                batch = await _run_batch(
                    session, caller, proposal_id, settings.branch_approve_batch, batches == 0
                )
                await session.commit()
        except ProblemError as exc:
            if exc.code == "busy" and batches > 0:
                return _progress(proposal_id, approved, last, batches, False)
            raise
        except DBAPIError as exc:
            if is_contention(exc) and batches > 0:
                logger.warning("branch approval met contention after %d batches", batches)
                return _progress(proposal_id, approved, last, batches, False)
            raise
        last = batch
        if batch.approved == 0:
            break
        approved += batch.approved
        batches += 1
        if not batch.ready_left:
            break
    complete = last is not None and not last.ready_left
    return _progress(proposal_id, approved, last, batches, complete)


async def _run_batch(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, limit: int, first: bool
) -> _Batch:
    await decision_lock_service.acquire(session, caller.tenant_id)
    proposals = await proposal_repository.lock_open(session, caller.tenant_id)
    root = next((p for p in proposals if p.id == proposal_id), None) or (
        await proposal_repository.get(session, caller.tenant_id, proposal_id)
    )
    view = await load_view(session, caller.tenant_id, proposals)
    if first:
        _ensure_root(caller, view, root)
    assert root is not None
    candidates = _members(view, proposals, root)
    approved = await decision_service.approve_ready(
        session, caller, view, proposals, {p.id for p in candidates}, limit
    )
    members = [p for p in _members(view, proposals, root) if p.state in OPEN_STATES]
    skipped = sum(1 for p in members if not decision_service.may_approve(caller, view, p))
    ready_left = any(
        decision_service.may_approve(caller, view, p) and view.readiness(p)[0] for p in members
    )
    return _Batch(approved, skipped, len(members), ready_left)


def _members(view: OntologyView, proposals: list[Proposal], root: Proposal) -> list[Proposal]:
    """The root while it is open, then its branch among the open proposals."""
    branch = BranchIndex(view, [p for p in proposals if p.state in OPEN_STATES]).branch(root)
    return ([root] if root.state in OPEN_STATES else []) + branch


def _ensure_root(caller: Caller, view: OntologyView, root: Proposal | None) -> None:
    if root is None or not can_read_proposal(caller.grants, proposal_company_ids(root)):
        raise not_found("proposal")
    if not holds_approving_role(caller.grants):
        raise forbidden("Only a Governor or Owner can approve")
    if root.type not in ROOT_TYPES:
        raise conflict("branch_root_invalid", "only a new concept or specialisation roots a branch")
    # An approved root continues its branch: a call that stopped at the round limit is
    # followed by another on the same root.
    if root.state is ProposalState.REJECTED:
        raise conflict("proposal_decided", "the proposal is already rejected")
    if not decision_service.may_approve(caller, view, root):
        raise forbidden("Your roles do not let you approve proposals in this scope")


def _progress(
    proposal_id: uuid.UUID, approved: int, last: _Batch | None, batches: int, complete: bool
) -> BranchResult:
    return BranchResult(
        root_id=proposal_id,
        approved=approved,
        skipped=last.skipped if last else 0,
        remaining=last.remaining if last else 0,
        batches=batches,
        complete=complete,
    )
