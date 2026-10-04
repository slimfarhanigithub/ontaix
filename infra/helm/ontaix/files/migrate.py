"""Applies every pending migration and prints the revision the database is at.

Runs in the API image before the API process starts. The database URL comes from the settings
(the environment, or the `.env` file the pod fetched from Key Vault) and is handed to alembic
through the environment; it is never printed.
"""

from __future__ import annotations

import logging
import os
import sys

from alembic.config import main as alembic

from app.config import get_settings


def main() -> int:
    logging.basicConfig(level="INFO")
    url = get_settings().database_url
    if not url:
        print("ONTAIX_DATABASE_URL is not set", file=sys.stderr)
        return 2
    os.environ["ONTAIX_DATABASE_URL"] = url
    alembic(argv=["upgrade", "head"])
    alembic(argv=["current"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
