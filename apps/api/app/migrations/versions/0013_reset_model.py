"""The model reset: the change kind `reset_model`.

Brings a database of revision 0012 to the current `contracts/schema.sql`. The statement is
idempotent, so on a database revision 0001 already created from the current contract this
revision changes nothing.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UPGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'reset_model';
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` stays literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0013 is one-way: PostgreSQL cannot drop an enum value")
