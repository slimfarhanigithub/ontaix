"""`python -m app.seed`: migrate the database, then load the demo tenant if it is not there yet."""

from __future__ import annotations

import asyncio
import logging
import sys

from app.clients.db_client import configure_engine, dispose_engine, get_session_factory
from app.config import get_settings
from app.migrations.runner import upgrade_to_head
from app.services.seed_service import seed_demo_tenant

logger = logging.getLogger(__name__)


async def _run(database_url: str) -> int:
    configure_engine(database_url)
    try:
        async with get_session_factory()() as session:
            created = await seed_demo_tenant(session)
            await session.commit()
    finally:
        await dispose_engine()
    logger.info("demo tenant %s", "seeded" if created else "already present, nothing changed")
    return 0


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.database_url:
        logger.error("ONTAIX_DATABASE_URL is not set")
        return 2
    if sys.platform == "win32":
        # psycopg's async driver needs a selector loop; Windows defaults to the proactor loop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    upgrade_to_head(settings.database_url)
    return asyncio.run(_run(settings.database_url))


if __name__ == "__main__":
    sys.exit(main())
