"""Initial schema: executes the DDL of contracts/schema.sql verbatim.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL_ENV = "ONTAIX_SCHEMA_SQL"
# The contract's path inside the repository, looked for above this file when the variable is
# not set (a checkout); the API image sets the variable to the copy it carries.
SCHEMA_SQL_IN_REPOSITORY = Path("contracts") / "schema.sql"


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters, so `%` in PL/pgSQL is literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(_contract_ddl())


def downgrade() -> None:
    op.execute("DROP SCHEMA ontaix CASCADE")


def _contract_ddl() -> str:
    """Read the schema contract and drop its own BEGIN/COMMIT so Alembic owns the transaction."""
    path = schema_sql_path(Path(__file__), os.environ)
    # Lines end at "\n" only: `str.splitlines` would also cut at U+2028 and other Unicode line
    # separators, which regex character classes of the contract hold as literal characters.
    statements = [
        line
        for line in path.read_text(encoding="utf-8").split("\n")
        if line.strip() not in {"BEGIN;", "COMMIT;"}
    ]
    return "\n".join(statements)


def schema_sql_path(module_file: Path, environment: Mapping[str, str]) -> Path:
    """The schema contract to execute: ONTAIX_SCHEMA_SQL when set, else contracts/schema.sql in
    the nearest directory above `module_file` that holds one. Resolved when the migration runs,
    never at import, and any depth of `module_file` is acceptable."""
    configured = environment.get(SCHEMA_SQL_ENV)
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise FileNotFoundError(f"{SCHEMA_SQL_ENV} points at {path}, which is not a file")
        return path
    for parent in module_file.resolve().parents:
        candidate = parent / SCHEMA_SQL_IN_REPOSITORY
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"schema contract {SCHEMA_SQL_IN_REPOSITORY} not found above {module_file}; set"
        f" {SCHEMA_SQL_ENV} to its location"
    )
