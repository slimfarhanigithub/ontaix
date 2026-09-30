"""The periodic purge of expired document and ontology imports, run by the API process for its
lifetime.

Every interval it deletes, in its own transaction, each document import and each ontology
import more than 24 hours past its expiry (sentences cascade). The delete is idempotent, so
several processes purging at once only repeat work. A failed round is logged and the next
round runs on schedule.
"""

from __future__ import annotations

import asyncio
import logging

from app.clients.db_client import platform_session
from app.services import import_service, ontology_import_service

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 15 * 60


async def purge_once() -> int:
    """One purge round in its own transaction; returns how many imports were deleted."""
    async with platform_session() as session:
        deleted = await import_service.purge_expired(session)
        deleted += await ontology_import_service.purge_expired(session)
        await session.commit()
    if deleted:
        logger.info("purged %d expired imports", deleted)
    return deleted


async def purge_periodically(interval_seconds: float = PURGE_INTERVAL_SECONDS) -> None:
    """Purge now and then every `interval_seconds` until cancelled."""
    while True:
        try:
            await purge_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("the import purge failed; retrying in %.0f s", interval_seconds)
        await asyncio.sleep(interval_seconds)
