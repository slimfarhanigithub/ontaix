"""Initial schema: executes the DDL of contracts/schema.sql verbatim.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL_ENV = "ONTAIX_SCHEMA_SQL"
REPO_SCHEMA_SQL = Path(__file__).resolve().parents[5] / "contracts" / "schema.sql"


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters, so `%` in PL/pgSQL is literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(_contract_ddl())


def downgrade() -> None:
    op.execute("DROP SCHEMA ontaix CASCADE")


def _contract_ddl() -> str:
    """Read the schema contract and drop its own BEGIN/COMMIT so Alembic owns the transaction."""
    path = Path(os.environ.get(SCHEMA_SQL_ENV) or REPO_SCHEMA_SQL)
    if not path.is_file():
        raise FileNotFoundError(
            f"schema contract not found at {path}; set {SCHEMA_SQL_ENV} to its location"
        )
    # Lines end at "\n" only: `str.splitlines` would also cut at U+2028 and other Unicode line
    # separators, which regex character classes of the contract hold as literal characters.
    statements = [
        line
        for line in path.read_text(encoding="utf-8").split("\n")
        if line.strip() not in {"BEGIN;", "COMMIT;"}
    ]
    return "\n".join(statements)
