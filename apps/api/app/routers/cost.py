"""GET /cost: Cost management figures for one month."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter

from app.auth import CallerDependency, SessionDependency
from app.models.api.cost import CostSummary
from app.services import cost_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agents"])


@router.get("/cost", response_model=CostSummary)
async def get_cost(
    session: SessionDependency, caller: CallerDependency, month: date | None = None
) -> CostSummary:
    return await cost_service.summary(session, caller, month)
