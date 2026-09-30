"""`python -m app.seed`: migrate the database, then load the demo tenant if it is not there yet.

Runs only when `ONTAIX_ENVIRONMENT` is `dev` or `test`. `ONTAIX_SEED` chooses what the tenant
holds: `fixture` (the default) the Northwind and Aurora example, `empty` only its settings and
directory. An existing tenant is never changed.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.clients.db_client import configure_engine, dispose_engine, platform_session
from app.config import SeedMode, get_settings
from app.migrations.runner import upgrade_to_head
from app.services.seed_service import seed_demo_tenant, seed_empty_tenant

logger = logging.getLogger(__name__)


async def _run(database_url: str, mode: SeedMode) -> int:
    configure_engine(database_url)
    seed = seed_empty_tenant if mode == "empty" else seed_demo_tenant
    try:
        async with platform_session() as session:
            created = await seed(session)
            await session.commit()
    finally:
        await dispose_engine()
    if created:
        logger.info("demo tenant seeded (%s)", mode)
    else:
        logger.info("demo tenant already present, nothing changed")
    return 0


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.environment not in ("dev", "test"):
        # The seed holds a full-access demo user and example data; it never loads elsewhere.
        logger.error("the seed runs only when ONTAIX_ENVIRONMENT is dev or test")
        return 2
    if not settings.database_url:
        logger.error("ONTAIX_DATABASE_URL is not set")
        return 2
    if sys.platform == "win32":
        # psycopg's async driver needs a selector loop; Windows defaults to the proactor loop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    upgrade_to_head(settings.database_url)
    return asyncio.run(_run(settings.database_url, settings.seed))


if __name__ == "__main__":
    sys.exit(main())
