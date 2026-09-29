"""Speech recognition tokens: the `speech` rate budget.

Brings a database of revision 0005 to the current `contracts/schema.sql`: redefines the budget
CHECK of `rate_budget_window` to accept `speech` and sets the table's comment. Both statements
are idempotent, so on a database revision 0001 already created from the current contract this
revision changes nothing. The DDL is the contract's text, so the constraint name and definition
match a database loaded from it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

ALTER TABLE rate_budget_window DROP CONSTRAINT IF EXISTS rate_budget_window_budget_check;
ALTER TABLE rate_budget_window ADD CONSTRAINT rate_budget_window_budget_check CHECK (budget IN ('import', 'parse', 'proposal', 'llm', 'expand', 'extraction', 'ocr', 'speech'));
COMMENT ON TABLE rate_budget_window IS 'Units spent per user or agent, per budget, per clock hour (window_start is a whole UTC hour), shared by every API replica. A charge of $n against $limit is one statement: INSERT INTO rate_budget_window (tenant_id, actor_kind, actor_id, budget, window_start, spent) SELECT $tenant, $kind, $actor, $budget, $window, $n WHERE $n <= $limit ON CONFLICT (tenant_id, actor_kind, actor_id, budget, window_start) DO UPDATE SET spent = rate_budget_window.spent + EXCLUDED.spent WHERE rate_budget_window.spent + EXCLUDED.spent <= $limit RETURNING spent; zero rows returned means the budget is exhausted and the call is refused (429 rate_limited, or llmOutcome rate_limited for the llm budget). The expand budget counts POST /concepts/{conceptId}/expand calls and is charged before the llm budget. The extraction budget counts whole-document extraction jobs started (POST /import/{importId}/extraction); the model calls of a job are bounded by its own token ceiling and the tenant cap, not by the per-call llm budget. The ocr budget counts OCR pages, charged for every image-only page before the OCR call. The speech budget counts POST /speech/token calls (ADR 0013). actor_id is a plain uuid so a charge never waits on a foreign key lock. A purge every 15 minutes deletes windows that started more than 2 hours ago.';
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0006 is one-way")
