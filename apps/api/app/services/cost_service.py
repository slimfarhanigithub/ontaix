"""`GET /cost`: the month's agent read figures and Ontaix's own language model usage.

The agent figures (`measuredEur`, `byPlatform`) are agent reads through the gateway; the `llm`
block is the language model and OCR calls Ontaix made itself, from its cost records.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.cost import CostSummary, PlatformCost
from app.models.api.settings import (
    DEFAULT_LLM_MONTHLY_TOKEN_CAP,
    DEFAULT_OCR_MONTHLY_PAGE_CAP,
)
from app.repositories import (
    agent_month_usage_repository,
    agent_repository,
    cost_allocation_repository,
    tenant_settings_repository,
)
from app.services import llm_usage_service
from app.utilities.clock import get_clock
from app.utilities.permissions import can_manage
from app.utilities.problems import forbidden

logger = logging.getLogger(__name__)


async def summary(session: AsyncSession, caller: Caller, month: date | None) -> CostSummary:
    if not can_manage(caller.grants):
        raise forbidden("Cost management requires Administrator")
    first = llm_usage_service.month_of(get_clock().now()) if month is None else month
    first = date(first.year, first.month, 1)
    counts = await agent_repository.counts(session, caller.tenant_id)
    platforms = await agent_month_usage_repository.by_platform(session, caller.tenant_id, first)
    allocated = await cost_allocation_repository.allocated_eur(session, caller.tenant_id, first)
    settings = await tenant_settings_repository.get(session, caller.tenant_id)
    cap = settings.llm_monthly_token_cap if settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
    page_cap = settings.ocr_monthly_page_cap if settings else DEFAULT_OCR_MONTHLY_PAGE_CAP
    measured = sum(p.cost_eur for p in platforms)
    return CostSummary(
        month=first,
        measured_eur=round(measured, 2),
        allocated_eur=allocated,
        agents_registered=counts.registered,
        agents_with_access=counts.with_access,
        reads=sum(p.reads for p in platforms),
        by_platform=[
            PlatformCost(
                platform=p.platform,
                agents_with_access=p.agents_with_access,
                cost_eur=round(p.cost_eur, 2),
                share_percent=round(p.cost_eur / measured * 100) if measured else 0,
            )
            for p in platforms
        ],
        llm=await llm_usage_service.month_usage(caller.tenant_id, first, cap, page_cap),
    )
