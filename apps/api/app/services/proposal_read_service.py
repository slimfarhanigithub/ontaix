"""Proposal reads: the paged list and the single read, plus the generic create and batch."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ProposalBatch
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.proposal import Proposal
from app.repositories import proposal_repository
from app.services import learning_capture_service, proposal_service, provenance_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_branch_service import OPEN_STATES, BranchIndex, annotate
from app.services.rate_limit_service import Budget, charge
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.listing import ListQuery, paginate
from app.utilities.permissions import can_read_proposal, can_read_tenant
from app.utilities.problems import forbidden, not_found
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

FILTERABLE = ("state", "type", "companyId", "proposerKind")
SORTABLE = ("createdAt",)
DEFAULT_STATES = ["pending", "half_approved"]


async def list_proposals(
    session: AsyncSession, caller: Caller, query: ListQuery
) -> PageOf[ProposalDto]:
    if not can_read_tenant(caller.grants):
        raise forbidden("No role grants you access to the model")
    proposals = await proposal_repository.list_for_tenant(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    states = query.filters.get("state", DEFAULT_STATES)
    rows = [
        p
        for p in proposals
        if p.state.value in states
        and can_read_proposal(caller.grants, proposal_company_ids(p))
        and ("type" not in query.filters or p.type.value in query.filters["type"])
        and (
            "companyId" not in query.filters
            or any(str(c) in query.filters["companyId"] for c in proposal_company_ids(p))
        )
        and (
            "proposerKind" not in query.filters
            or p.proposer_kind.value in query.filters["proposerKind"]
        )
    ]
    page, total = paginate(rows, query, {"createdAt": lambda p: p.created_at}, "createdAt")
    branches = BranchIndex(view, [p for p in proposals if p.state in OPEN_STATES])
    return PageOf[ProposalDto](
        items=[
            annotate(
                readable_proposal(caller.grants, view.proposal_dto(p, view.proposal_artefacts(p))),
                p,
                branches,
            )
            for p in page
        ],
        page=query.page,
        page_size=query.page_size,
        total=total,
    )


async def get_proposal(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID
) -> ProposalDto:
    proposal = await proposal_repository.get(session, caller.tenant_id, proposal_id)
    if proposal is None:
        raise not_found("proposal")
    view = await load_view(session, caller.tenant_id, [proposal])
    _ensure_readable(caller, view, proposal)
    branches = BranchIndex(view, await proposal_repository.list_open(session, caller.tenant_id))
    dto = view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    return annotate(readable_proposal(caller.grants, dto), proposal, branches)


async def create_proposal(session: AsyncSession, caller: Caller, draft) -> ProposalDto:
    await charge(Budget.PROPOSAL, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    view = await load_view(session, caller.tenant_id)
    [provenance] = await provenance_service.resolve(session, caller, view, [draft])
    proposal = await proposal_service.create(session, caller, view, draft, provenance=provenance)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


async def create_batch(
    session: AsyncSession, caller: Caller, batch: ProposalBatch
) -> list[ProposalDto]:
    """One proposal unit per draft is charged for the whole call before anything is created."""
    drafts = provenance_service.with_batch_defaults(batch)
    await charge(
        Budget.PROPOSAL, caller.tenant_id, caller.actor_kind.value, caller.user_id, len(drafts)
    )
    view = await load_view(session, caller.tenant_id)
    provenances = await provenance_service.resolve(session, caller, view, drafts)
    created = await proposal_service.create_batch(session, caller, view, drafts, provenances)
    await learning_capture_service.link_batch(session, caller, batch.parse_id, drafts, created)
    return [
        readable_proposal(caller.grants, view.proposal_dto(p, view.proposal_artefacts(p)))
        for p in created
    ]


def _ensure_readable(caller: Caller, view: OntologyView, proposal: Proposal) -> None:
    """A proposal is readable when the caller reads every company it touches."""
    if not can_read_proposal(caller.grants, proposal_company_ids(proposal)):
        raise not_found("proposal")
