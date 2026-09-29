"""Teach extraction: shared rate budgets, teach sessions, language model cost and token usage.

Brings a database of revision 0002 to the current `contracts/schema.sql`: adds
`tenant_settings.llm_monthly_token_cap` with its CHECK and the new table comment, the
`llm_call`, `llm_month_usage`, `rate_budget_window` and `teach_session_turn` tables with their
indexes and comments, and redefines the file-name CHECKs of `document_import` and `proposal`,
which also refuse the zero-width characters U+200B to U+200D and U+2028 and U+2029. Every
statement is idempotent, so on a database revision 0001 already created from the current
contract this revision changes nothing. The DDL is the contract's text, so constraint names and
definitions match a database loaded from it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS llm_monthly_token_cap bigint NOT NULL DEFAULT 2000000 CHECK (llm_monthly_token_cap BETWEEN 0 AND 1000000000);
COMMENT ON TABLE tenant_settings IS 'The 22 tenant settings plus appearance, the connector egress allowlist and the monthly token cap of Ontaix''s own language model calls (default 2,000,000, so the teach extraction model step is on; 0 turns it off and is how an administrator opts out); the two locked settings are enforced by CHECK constraints.';

CREATE TABLE IF NOT EXISTS llm_call (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  actor_kind     actor_kind NOT NULL CHECK (actor_kind IN ('user', 'agent')),
  actor_id       uuid NOT NULL,
  company_id     uuid,
  purpose        text NOT NULL CHECK (purpose IN ('teach_extraction')),
  provider       text NOT NULL CHECK (provider ~ '^[a-z0-9][a-z0-9_.-]{0,59}$'),
  model          text NOT NULL CHECK (char_length(model) BETWEEN 1 AND 120 AND model ~ '^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$'),
  input_tokens   integer NOT NULL CHECK (input_tokens >= 0),
  output_tokens  integer NOT NULL CHECK (output_tokens >= 0),
  cost_eur       numeric(12,6) NOT NULL CHECK (cost_eur >= 0),
  latency_ms     integer NOT NULL CHECK (latency_ms BETWEEN 0 AND 60000),
  outcome        text NOT NULL CHECK (outcome IN ('used', 'invalid_output', 'timeout', 'provider_error')),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS llm_call_by_month ON llm_call (tenant_id, occurred_at);
CREATE INDEX IF NOT EXISTS llm_call_by_occurred ON llm_call (occurred_at);
COMMENT ON TABLE llm_call IS 'One cost record per call Ontaix makes to a language model provider, including failed and timed-out calls: who caused it (actor_id and company_id are plain uuids so the record survives the actor or company), why (purpose), which provider and model, token counts, the estimated euro cost from the deployment price table, latency and outcome. It never holds the sentence, the prompt, the answer or any credential. Cost management sums it per month; a purge deletes rows older than 400 days across all tenants through llm_call_by_occurred. It is inserted in its own short transaction after the call, never inside the request transaction.';

CREATE TABLE IF NOT EXISTS llm_month_usage (
  tenant_id  uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  month      date NOT NULL CHECK (month = date_trunc('month', month)::date),
  tokens     bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
  PRIMARY KEY (tenant_id, month)
);
COMMENT ON TABLE llm_month_usage IS 'Tokens counted against tenant_settings.llm_monthly_token_cap per calendar month (UTC). Before a call the API reserves its upper bound (estimated input plus the maximum output tokens) with INSERT ... SELECT $reserve WHERE $reserve <= $cap ON CONFLICT (tenant_id, month) DO UPDATE SET tokens = llm_month_usage.tokens + EXCLUDED.tokens WHERE llm_month_usage.tokens + EXCLUDED.tokens <= $cap RETURNING tokens; zero rows returned means the cap is reached and the model step is skipped. The reservation commits in its own short transaction before the provider is called, never inside the request transaction, so no row lock is held during the call. After the call, in another short transaction, it settles with UPDATE ... SET tokens = greatest(tokens + $actual - $reserved, 0) WHERE tenant_id = $tenant AND month = $reserved_month, always the month the reservation was made in, even when the call ends in the next month. A call that times out or fails settles its actual count (0 when the provider reports none), which releases the rest of the reservation. A reservation whose process dies before settling stays counted until the month ends. Shared by every API replica.';

CREATE TABLE IF NOT EXISTS rate_budget_window (
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_kind    actor_kind NOT NULL CHECK (actor_kind IN ('user', 'agent')),
  actor_id      uuid NOT NULL,
  budget        text NOT NULL CHECK (budget IN ('import', 'parse', 'proposal', 'llm')),
  window_start  timestamptz NOT NULL CHECK (extract(epoch FROM window_start) = floor(extract(epoch FROM window_start) / 3600) * 3600),
  spent         integer NOT NULL CHECK (spent >= 0),
  PRIMARY KEY (tenant_id, actor_kind, actor_id, budget, window_start)
);
CREATE INDEX IF NOT EXISTS rate_budget_window_by_start ON rate_budget_window (window_start);
COMMENT ON TABLE rate_budget_window IS 'Units spent per user or agent, per budget, per clock hour (window_start is a whole UTC hour), shared by every API replica. A charge of $n against $limit is one statement: INSERT INTO rate_budget_window (tenant_id, actor_kind, actor_id, budget, window_start, spent) SELECT $tenant, $kind, $actor, $budget, $window, $n WHERE $n <= $limit ON CONFLICT (tenant_id, actor_kind, actor_id, budget, window_start) DO UPDATE SET spent = rate_budget_window.spent + EXCLUDED.spent WHERE rate_budget_window.spent + EXCLUDED.spent <= $limit RETURNING spent; zero rows returned means the budget is exhausted and the call is refused (429 rate_limited, or llmOutcome rate_limited for the llm budget). actor_id is a plain uuid so a charge never waits on a foreign key lock. A purge every 15 minutes deletes windows that started more than 2 hours ago.';

CREATE TABLE IF NOT EXISTS teach_session_turn (
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_kind   actor_kind NOT NULL CHECK (actor_kind IN ('user', 'agent')),
  actor_id     uuid NOT NULL,
  company_id   uuid NOT NULL,
  session_id   uuid NOT NULL,
  turn_index   integer NOT NULL CHECK (turn_index >= 0),
  sentence     text NOT NULL CHECK (char_length(sentence) BETWEEN 1 AND 400),
  extractor    text NOT NULL CHECK (extractor IN ('rules', 'llm', 'rules+llm')),
  concept_ids  uuid[] NOT NULL DEFAULT '{}',
  new_labels   text[] NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL DEFAULT now() + interval '2 hours',
  PRIMARY KEY (tenant_id, actor_kind, actor_id, company_id, session_id, turn_index),
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT teach_session_turn_concept_ids CHECK (
    cardinality(concept_ids) <= 50 AND array_position(concept_ids, NULL) IS NULL
  ),
  CONSTRAINT teach_session_turn_new_labels CHECK (
    cardinality(new_labels) <= 50
    AND array_position(new_labels, NULL) IS NULL
    AND char_length(array_to_string(new_labels, '')) <= 6000
  ),
  CONSTRAINT teach_session_turn_two_hours CHECK (expires_at = created_at + interval '2 hours')
);
CREATE INDEX IF NOT EXISTS teach_session_turn_by_expiry ON teach_session_turn (expires_at);
COMMENT ON TABLE teach_session_turn IS 'The recent sentences of one teach bar session, so the teach extraction model step can resolve back-references. Keyed by tenant, caller (actor_kind, actor_id), company and the client-generated session_id; only that caller reads it. concept_ids are the existing concepts the sentence referenced (re-checked at read time: a stored id is used only if the concept still exists and would be a valid candidate now - taught company, or another company only while crossCompany is on and the caller may read it), new_labels the labels it introduced (resolved to ids at the next sentence when a proposal has created them). Turns are stored in one short transaction after the parse result is built: SELECT pg_advisory_xact_lock(hashtextextended(tenant_id || '':'' || actor_kind || '':'' || actor_id || '':'' || company_id || '':'' || session_id, 0)); INSERT ... SELECT coalesce(max(turn_index) + 1, 0) FROM teach_session_turn WHERE <session key>; DELETE the same session''s turns with turn_index <= n - 8. The advisory lock serialises concurrent sentences of one session, so turn numbers never collide and at most 8 turns are kept. If storing the turn fails anyway, the turn is not kept and the parse still answers 200; it is never an error. Reads ignore rows past expires_at (2 hours after each sentence); a purge every 15 minutes deletes them.';

ALTER TABLE document_import DROP CONSTRAINT IF EXISTS document_import_file_name;
ALTER TABLE document_import ADD CONSTRAINT document_import_file_name CHECK (
    char_length(file_name) BETWEEN 1 AND 255
    AND octet_length(file_name) <= 1020
    AND file_name !~ '[/\\:\x01-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u061c\u2066-\u2069\ufeff]'
  );

ALTER TABLE proposal DROP CONSTRAINT IF EXISTS proposal_origin_detail_shape;
ALTER TABLE proposal ADD CONSTRAINT proposal_origin_detail_shape CHECK (
    origin_detail IS NULL OR COALESCE((
      jsonb_typeof(origin_detail) = 'object'
      AND octet_length(origin_detail::text) <= 2048
      AND origin_detail ? 'fileName'
      AND origin_detail ? 'mediaType'
      AND origin_detail ? 'sentenceIndex'
      AND (origin_detail - 'fileName' - 'mediaType' - 'sentenceIndex' - 'position') = '{}'::jsonb
      AND jsonb_typeof(origin_detail -> 'fileName') = 'string'
      AND char_length(origin_detail ->> 'fileName') BETWEEN 1 AND 255
      AND octet_length(origin_detail ->> 'fileName') <= 1020
      AND (origin_detail ->> 'fileName') !~ '[/\\:\x01-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u061c\u2066-\u2069\ufeff]'
      AND jsonb_typeof(origin_detail -> 'mediaType') = 'string'
      AND (origin_detail ->> 'mediaType') IN (
        'text/plain', 'text/markdown', 'text/csv', 'application/json',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf')
      AND jsonb_typeof(origin_detail -> 'sentenceIndex') = 'number'
      AND (origin_detail ->> 'sentenceIndex') ~ '^[0-9]{1,4}$'
      AND (origin_detail ->> 'sentenceIndex')::integer <= 1999
      AND (NOT (origin_detail ? 'position') OR (
        jsonb_typeof(origin_detail -> 'position') = 'object'
        AND ((origin_detail -> 'position') - 'unit' - 'index') = '{}'::jsonb
        AND (origin_detail -> 'position' ->> 'unit') IN ('page', 'paragraph')
        AND jsonb_typeof(origin_detail -> 'position' -> 'index') = 'number'
        AND (origin_detail -> 'position' ->> 'index') ~ '^[0-9]{1,6}$'
        AND (origin_detail -> 'position' ->> 'index')::integer BETWEEN 1 AND 100000
      ))
    ), false)
  );
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0003 is one-way")
