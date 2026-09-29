"""The periodic purge of short-lived rows, run by the API process for its lifetime.

Every interval it deletes, each in its own transaction: rate budget windows that started more
than 2 hours ago, expired teach session turns, and language model cost records older than 400
days. Every delete is idempotent, so several processes purging at once only repeat work. A
failed round is logged and the next round runs on schedule.
"""

from __future__ import annotations

import asyncio
import logging

from app.services import llm_usage_service, rate_limit_service, teach_session_service

logger = logging.getLogger(__name__)


async def purge_once() -> None:
    windows = await rate_limit_service.purge_old_windows()
    turns = await teach_session_service.purge_expired()
    calls = await llm_usage_service.purge_old_calls()
    if windows or turns or calls:
        logger.info(
            "purged %d budget windows, %d teach session turns, %d cost records",
            windows,
            turns,
            calls,
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
