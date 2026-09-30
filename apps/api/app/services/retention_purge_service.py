"""The periodic purge of short-lived rows, run by the API process for its lifetime.

Every interval it deletes, each in its own transaction: rate budget windows that started more
than 2 hours ago, expired teach session turns, language model cost records older than 400 days,
concept expansions and whole-document extraction results more than 24 hours past their expiry,
failed or cancelled extraction jobs 48 hours after they ended, teach parse records past their
expiry, and lessons and aliases retired more than 30 days ago. Every delete is idempotent,
so several processes purging at once only repeat work. A failed round is logged and the next
round runs on schedule.
"""

from __future__ import annotations

import asyncio
import logging

from app.services import (
    concept_expansion_service,
    document_extraction_service,
    learning_service,
    llm_usage_service,
    rate_limit_service,
    teach_session_service,
)

logger = logging.getLogger(__name__)


async def purge_once() -> None:
    windows = await rate_limit_service.purge_old_windows()
    turns = await teach_session_service.purge_expired()
    calls = await llm_usage_service.purge_old_calls()
    expansions = await concept_expansion_service.purge_expired()
    jobs = await document_extraction_service.purge_expired()
    parses, retired = await learning_service.purge_expired()
    if windows or turns or calls or expansions or jobs or parses or retired:
        logger.info(
            "purged %d budget windows, %d teach session turns, %d cost records, %d expansions,"
            " %d extraction jobs, %d teach parses, %d retired lessons and aliases",
            windows,
            turns,
            calls,
            expansions,
            jobs,
            parses,
            retired,
        )


async def purge_periodically(interval_seconds: float) -> None:
    """Purge now and then every `interval_seconds` until cancelled."""
    while True:
        try:
            await purge_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("the retention purge failed; retrying in %.0f s", interval_seconds)
        await asyncio.sleep(interval_seconds)
