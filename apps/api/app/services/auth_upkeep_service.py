"""The sign-in upkeep run by the API process for its lifetime (platform role).

Every interval, each in its own transaction: support grants past their 60 minutes are cleared
and their end is audited with the system as actor, and throttle keys whose window and lock have
both passed are deleted. Both are idempotent, so several processes running them only repeat
work. A failed round is logged and the next round runs on schedule.
"""

from __future__ import annotations

import asyncio
import logging

from app.clients.db_client import platform_session
from app.repositories import sign_in_throttle_repository
from app.services import support_session_service

logger = logging.getLogger(__name__)

UPKEEP_INTERVAL_SECONDS = 60.0


async def run_once() -> None:
    async with platform_session() as session:
        closed = await support_session_service.close_expired(session)
        await session.commit()
    async with platform_session() as session:
        purged = await sign_in_throttle_repository.purge_stale(session)
        await session.commit()
    if closed or purged:
        logger.info("ended %d expired support sessions, purged %d throttle keys", closed, purged)


async def run_periodically(interval_seconds: float = UPKEEP_INTERVAL_SECONDS) -> None:
    """Run now and then every `interval_seconds` until cancelled."""
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("the sign-in upkeep failed; retrying in %.0f s", interval_seconds)
        await asyncio.sleep(interval_seconds)
