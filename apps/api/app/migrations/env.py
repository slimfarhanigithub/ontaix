"""Alembic environment: runs migrations over a synchronous psycopg 3 connection.

The URL comes from `ONTAIX_DATABASE_URL`, or from the `sqlalchemy.url` option when a caller
(the test fixture, the seed command) sets it programmatically. Each revision runs and commits in
a transaction of its own: PostgreSQL lets a later revision use an enum value an earlier one
added only once that addition is committed.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from app.clients.db_client import ASYNC_DRIVER_PREFIX, async_database_url
from app.models.storage.base import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    url = configured or os.environ.get("ONTAIX_DATABASE_URL")
    if not url:
        raise RuntimeError("ONTAIX_DATABASE_URL is not set")
    return async_database_url(url).replace(ASYNC_DRIVER_PREFIX, "postgresql+psycopg://")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=None)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
