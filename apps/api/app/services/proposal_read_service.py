"""Proposal reads: the paged list and the single read, plus the generic create and batch."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.proposal import Proposal
from app.repositories import proposal_repository
from app.services import proposal_service
from app.services.company_service import readable_companies
from app.services.ontology_view_service import load_view
from app.utilities.listing import ListQuery, paginate
from app.utilities.permissions import can_read_tenant
from app.utilities.problems import forbidden, not_found

logger = logging.getLogger(__name__)

FILTERABLE = ("state", "type", "companyId", "proposerKind")
SORTABLE = ("createdAt",)
DEFAULT_STATES = ["pending", "half_approved"]


async def list_proposals(
    session: AsyncSession, caller: Caller, query: ListQuery
) -> PageOf[ProposalDto]:
    if not can_read_tenant(caller.grants):
        raise forbidden("no role grants you access to the model")
    proposals = await proposal_repository.list_for_tenant(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, proposals)
    readable = {c.id for c in readable_companies(caller, view)}
    states = query.filters.get("state", DEFAULT_STATES)
    rows = [
        p
        for p in proposals
        if p.state.value in states
        and (p.company_id is None or p.company_id in readable)
        and ("type" not in query.filters or p.type.value in query.filters["type"])
        and ("companyId" not in query.filters or str(p.company_id) in query.filters["companyId"])
        and (
            "proposerKind" not in query.filters
            or p.proposer_kind.value in query.filters["proposerKind"]
        )
    ]
    page, total = paginate(rows, query, {"createdAt": lambda p: p.created_at}, "createdAt")
    return PageOf[ProposalDto](
        items=[view.proposal_dto(p, view.proposal_artefacts(p)) for p in page],
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
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


async def create_proposal(session: AsyncSession, caller: Caller, draft) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    proposal = await proposal_service.create(session, caller, view, draft)
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


async def create_batch(session: AsyncSession, caller: Caller, drafts: list) -> list[ProposalDto]:
    view = await load_view(session, caller.tenant_id)
    created = await proposal_service.create_batch(session, caller, view, drafts)
    return [view.proposal_dto(p, view.proposal_artefacts(p)) for p in created]


def _ensure_readable(caller: Caller, view, proposal: Proposal) -> None:
    readable = {c.id for c in readable_companies(caller, view)}
    if proposal.company_id is not None and proposal.company_id not in readable:
        raise not_found("proposal")
