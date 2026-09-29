"""Taught attributes: an attribute holds either a source column and fill, or a stated value.

Brings the `attribute` table to the current `contracts/schema.sql`: `col` and `fill` become
nullable, the `value` column (1 to 200 characters) is added, and the CHECK
`attribute_read_or_taught` makes every row one of the two kinds - read from a source (col and
fill set, value null) or taught (value set, col, fill and source_id null, type text, number or
date). Every statement is idempotent, so on a database already created from the current contract
this revision changes nothing. The DDL is the contract's text, so constraint names and
definitions match a database loaded from it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

ALTER TABLE attribute ALTER COLUMN col DROP NOT NULL;
ALTER TABLE attribute ALTER COLUMN fill DROP NOT NULL;
ALTER TABLE attribute ADD COLUMN IF NOT EXISTS value text CHECK (char_length(value) BETWEEN 1 AND 200);
ALTER TABLE attribute DROP CONSTRAINT IF EXISTS attribute_read_or_taught;
ALTER TABLE attribute ADD CONSTRAINT attribute_read_or_taught CHECK (
    (value IS NULL) = (col IS NOT NULL)
    AND (col IS NULL) = (fill IS NULL)
    AND (value IS NULL OR (source_id IS NULL AND type IN ('text', 'number', 'date')))
  );
COMMENT ON TABLE attribute IS 'An attribute of a concept, approved or still proposed, of one of two kinds: read from a bound source (source column col and fill percentage, value null), or taught (value as a person stated it through teach extraction, col, fill and source_id null, type text, number or date).';
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0004 is one-way")
