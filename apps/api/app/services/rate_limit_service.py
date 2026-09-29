"""Per-actor hourly budgets for imports, teach parses, proposal creation, model calls, concept
expansions, whole-document extraction jobs, OCR pages and speech tokens.

Each actor of each tenant holds one budget per kind and clock hour (UTC), counted in the
`rate_budget_window` table that every API replica and worker shares. A charge takes every unit
it asks for or none, in one conditional upsert committed in its own short transaction, so units
spent survive a rolled-back request and a failed call still costs. A refused charge answers
`429 rate_limited` with `Retry-After` set to the seconds left in the hour; the `llm` budget is
never an error - the model step is skipped instead.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta
from enum import StrEnum

from app.auth import Caller
from app.clients.db_client import get_session_factory
from app.config import get_settings
from app.repositories import rate_budget_window_repository
from app.utilities.clock import get_clock
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 3600
RETAINED_WINDOWS = timedelta(hours=2)


class Budget(StrEnum):
    IMPORT = "import"
    PARSE = "parse"
    PROPOSAL = "proposal"
    LLM = "llm"
    OCR = "ocr"
    EXPAND = "expand"
    EXTRACTION = "extraction"
    SPEECH = "speech"


UNITS_PER_WINDOW: dict[Budget, int] = {
    Budget.IMPORT: 60,
    Budget.PARSE: 2000,
    Budget.PROPOSAL: 5000,
}


async def charge(
    budget: Budget, tenant_id: uuid.UUID, actor_kind: str, actor_id: uuid.UUID, units: int = 1
) -> None:
    """Spend `units` of the actor's budget, or refuse the whole call with `429`."""
    if units <= 0:
        return
    if await try_charge(budget, tenant_id, actor_kind, actor_id, units):
        return
    now = get_clock().now()
    retry_after = max(1, math.ceil((_window_start(now) - now).total_seconds() + WINDOW_SECONDS))
    raise ProblemError(
        429,
        "rate_limited",
        f"the {budget.value} budget of {limit_of(budget)} units per hour is spent",
        headers={"Retry-After": str(retry_after)},
    )


async def try_charge(
    budget: Budget, tenant_id: uuid.UUID, actor_kind: str, actor_id: uuid.UUID, units: int = 1
) -> bool:
    """Spend `units` in the current hour; False, spending nothing, when the budget cannot."""
    async with get_session_factory()() as session:
        spent = await rate_budget_window_repository.charge(
            session,
            tenant_id=tenant_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            budget=budget.value,
            window_start=_window_start(get_clock().now()),
            units=units,
            limit=limit_of(budget),
        )
        await session.commit()
    return spent is not None


async def charge_proposals(caller: Caller, drafts: int = 1) -> None:
    """One proposal unit per draft the caller's call creates, whatever the endpoint."""
    await charge(Budget.PROPOSAL, caller.tenant_id, caller.actor_kind.value, caller.user_id, drafts)


def limit_of(budget: Budget) -> int:
    settings = get_settings()
    if budget is Budget.LLM:
        return settings.llm_calls_per_hour
    if budget is Budget.EXPAND:
        return settings.expand_calls_per_hour
    if budget is Budget.EXTRACTION:
        return settings.document_extraction_jobs_per_hour
    if budget is Budget.OCR:
        return settings.ocr_pages_per_hour
    if budget is Budget.SPEECH:
        return settings.speech_tokens_per_hour
    return UNITS_PER_WINDOW[budget]


async def purge_old_windows() -> int:
    """Delete windows that started more than 2 hours ago, in its own transaction."""
    async with get_session_factory()() as session:
        deleted = await rate_budget_window_repository.delete_started_before(
            session, get_clock().now() - RETAINED_WINDOWS
        )
        await session.commit()
    return deleted


def _window_start(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)
