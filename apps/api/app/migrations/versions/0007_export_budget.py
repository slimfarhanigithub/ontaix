"""Export: the `export` rate budget.

Brings a database of revision 0006 to the budget CHECK of `rate_budget_window` in
`contracts/schema.sql`, which accepts `export` (ADR 0016). The statements are idempotent, so on
a database revision 0001 already created from the current contract this revision changes
nothing. The DDL is the contract's text, so the constraint name and definition match a database
loaded from it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

ALTER TABLE rate_budget_window DROP CONSTRAINT IF EXISTS rate_budget_window_budget_check;
ALTER TABLE rate_budget_window ADD CONSTRAINT rate_budget_window_budget_check CHECK (budget IN ('import', 'parse', 'proposal', 'llm', 'expand', 'extraction', 'ocr', 'speech', 'export'));
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0007 is one-way")
