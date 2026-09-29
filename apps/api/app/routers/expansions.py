"""POST /expansions/{expansionId}/proposals: a selection of stored suggestions to proposals."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.expansion import ExpansionSelection
from app.models.api.proposal import Proposal
from app.services import expansion_proposal_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Proposals"])


@router.post(
    "/expansions/{expansion_id}/proposals",
    response_model=list[Proposal],
    status_code=status.HTTP_202_ACCEPTED,
)
async def propose_expansion(
    expansion_id: uuid.UUID,
    body: ExpansionSelection,
    session: SessionDependency,
    caller: CallerDependency,
) -> list[Proposal]:
    return await expansion_proposal_service.propose(session, caller, expansion_id, body)
