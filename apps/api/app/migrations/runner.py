"""Programmatic entry point for `alembic upgrade head`, used by the seed command and tests."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

API_ROOT = Path(__file__).resolve().parents[2]


def upgrade_to_head(database_url: str) -> None:
    """Apply every pending migration to the database at `database_url`."""
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "app" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")
