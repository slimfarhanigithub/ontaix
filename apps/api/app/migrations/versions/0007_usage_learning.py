"""Usage learning: the company switch, teach parse records, proposal sources, lessons, aliases.

Brings a database of revision 0006 to the current `contracts/schema.sql`: the column
`company.learning` and the table's comment, and the tables `teach_parse`,
`proposal_learning_source`, `learning_example` and `company_alias` with their indexes and
comments. Every statement is idempotent, so on a database revision 0001 already created from the
current contract this revision changes nothing. The DDL is the contract's text, so constraint
names and definitions match a database loaded from it.

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

ALTER TABLE company ADD COLUMN IF NOT EXISTS learning boolean NOT NULL DEFAULT true;
COMMENT ON TABLE company IS 'A business-as-a-product in the tenant; the home company (position 0) cannot be removed. learning turns usage learning on or off for the company (ADR 0014; Administrator only, audited).';

CREATE TABLE IF NOT EXISTS teach_parse (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  company_id     uuid NOT NULL,
  actor_user_id  uuid NOT NULL,
  session_id     uuid,
  origin         proposal_origin NOT NULL CHECK (origin IN ('text', 'speech', 'document')),
  source_text    text NOT NULL CHECK (char_length(source_text) BETWEEN 1 AND 4000),
  extractor      text NOT NULL CHECK (extractor IN ('rules', 'llm', 'rules+llm')),
  model_output   jsonb NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz NOT NULL DEFAULT now() + interval '7 days',
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT teach_parse_model_output_shape CHECK (
    jsonb_typeof(model_output) = 'object'
    AND model_output ? 'intents' AND model_output ? 'drafts'
    AND octet_length(model_output::text) <= 262144
  ),
  CONSTRAINT teach_parse_seven_days CHECK (expires_at = created_at + interval '7 days')
);
CREATE INDEX IF NOT EXISTS teach_parse_by_expiry ON teach_parse (expires_at);
CREATE INDEX IF NOT EXISTS teach_parse_by_session ON teach_parse (tenant_id, company_id, actor_user_id, session_id, created_at DESC);
COMMENT ON TABLE teach_parse IS 'The record of one POST /teach/parse by a user while usage learning is on for the company (ADR 0014): the source text (typed sentence, speech request text or cited document sentence), its origin, the extractor and a snapshot of what the parse produced (intents and drafts). A later POST /proposals/batch citing it with parseId links each proposal to it in proposal_learning_source. It is the raw material of lessons, not a lesson; it is never sent to a model. Agents are never recorded: only human-decided cases teach. A purge every 15 minutes deletes rows past expires_at, 7 days after the parse.';

CREATE TABLE IF NOT EXISTS proposal_learning_source (
  proposal_id   uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('teach', 'expand', 'extraction')),
  parse_id      uuid,
  expansion_id  uuid,
  job_id        uuid,
  draft_index   integer NOT NULL CHECK (draft_index BETWEEN 0 AND 4999),
  edited        boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, proposal_id) REFERENCES proposal(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, parse_id) REFERENCES teach_parse(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, expansion_id) REFERENCES concept_expansion(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, job_id) REFERENCES document_extraction_job(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT proposal_learning_source_one_source CHECK (
    (kind = 'teach'      AND parse_id IS NOT NULL AND expansion_id IS NULL AND job_id IS NULL) OR
    (kind = 'expand'     AND expansion_id IS NOT NULL AND parse_id IS NULL AND job_id IS NULL AND NOT edited) OR
    (kind = 'extraction' AND job_id IS NOT NULL AND parse_id IS NULL AND expansion_id IS NULL AND NOT edited)
  )
);
COMMENT ON TABLE proposal_learning_source IS 'Which model output a proposal came from, written in the transaction that creates the proposal: a teach parse and the index of the matching draft (edited true when the submitted draft differs from every draft the parse stored, which the capture reads as a correction), an expansion, or a whole-document extraction job. Removed with its source when the source is purged; a decision after that teaches nothing.';

CREATE TABLE IF NOT EXISTS learning_example (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  company_id       uuid NOT NULL,
  signal           text NOT NULL CHECK (signal IN ('approve', 'reject', 'correct')),
  task             text NOT NULL CHECK (task IN ('teach', 'expand', 'extraction')),
  origin           proposal_origin NOT NULL CHECK (origin IN ('text', 'speech', 'document', 'suggestion')),
  source_text      text NOT NULL CHECK (char_length(source_text) BETWEEN 1 AND 4000),
  model_output     jsonb,
  final_structure  jsonb,
  proposal_ids     uuid[] NOT NULL DEFAULT '{}',
  concept_ids      uuid[] NOT NULL DEFAULT '{}',
  corrects_id      uuid,
  bulk             boolean NOT NULL DEFAULT false,
  actor_user_id    uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  retired_at       timestamptz,
  retired_reason   text CHECK (retired_reason IN ('contradicted', 'superseded', 'cap')),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, corrects_id) REFERENCES learning_example(tenant_id, id) ON DELETE SET NULL (corrects_id),
  CONSTRAINT learning_example_signal_shape CHECK (
    (signal = 'approve' AND final_structure IS NOT NULL AND corrects_id IS NULL) OR
    (signal = 'reject'  AND model_output IS NOT NULL AND final_structure IS NULL AND corrects_id IS NULL AND NOT bulk) OR
    (signal = 'correct' AND model_output IS NOT NULL AND final_structure IS NOT NULL AND NOT bulk)
  ),
  CONSTRAINT learning_example_json_shape CHECK (
    (model_output IS NULL OR (jsonb_typeof(model_output) = 'object' AND octet_length(model_output::text) <= 65536))
    AND (final_structure IS NULL OR (jsonb_typeof(final_structure) = 'object' AND octet_length(final_structure::text) <= 65536))
  ),
  CONSTRAINT learning_example_retired_pair CHECK ((retired_at IS NULL) = (retired_reason IS NULL)),
  CONSTRAINT learning_example_arrays CHECK (
    cardinality(proposal_ids) BETWEEN 1 AND 200 AND array_position(proposal_ids, NULL) IS NULL
    AND cardinality(concept_ids) <= 200 AND array_position(concept_ids, NULL) IS NULL
  ),
  CONSTRAINT learning_example_not_self CHECK (corrects_id IS NULL OR corrects_id <> id)
);
CREATE INDEX IF NOT EXISTS learning_example_active ON learning_example (tenant_id, company_id, created_at DESC) WHERE retired_at IS NULL;
CREATE INDEX IF NOT EXISTS learning_example_by_concept ON learning_example USING gin (concept_ids) WHERE retired_at IS NULL;
CREATE INDEX IF NOT EXISTS learning_example_by_retired ON learning_example (retired_at) WHERE retired_at IS NOT NULL;
COMMENT ON TABLE learning_example IS 'A lesson learnt from a human decision in one company (ADR 0014): approve (the source text and the structure a person approved), reject (the model output a person rejected, a negative example) or correct (what the model produced and what the person meant instead, linked to the rejected lesson by corrects_id). Written only from human decisions - a user approving, rejecting or re-teaching - never from agents, the model or the eval harness. bulk marks approvals made through approve-all or branch approval, ranked after individual ones; bulk rejections teach nothing. Read per company only, ranked by BM25 at each call. A lesson whose approved concept is later deleted is retired (contradicted); beyond 5,000 active lessons per company the oldest are retired (cap). Retired lessons are never read and are purged 30 days after retired_at; deleting a lesson, a reset, the company or the user removes rows at once.';

CREATE TABLE IF NOT EXISTS company_alias (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  company_id     uuid NOT NULL,
  heard          text NOT NULL,
  meant          text NOT NULL,
  concept_id     uuid,
  actor_user_id  uuid NOT NULL,
  hits           integer NOT NULL DEFAULT 0 CHECK (hits >= 0),
  created_at     timestamptz NOT NULL DEFAULT now(),
  retired_at     timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, concept_id) REFERENCES concept(tenant_id, id) ON DELETE SET NULL (concept_id),
  CONSTRAINT company_alias_text CHECK (
    char_length(heard) BETWEEN 1 AND 120 AND char_length(meant) BETWEEN 1 AND 120
    AND heard = btrim(heard) AND meant = btrim(meant)
    AND heard !~ '[<>\x01-\x1f\x7f-\x9f ­؜᠎​-‏ -‮⁠-⁤⁦-⁯﻿]'
    AND meant !~ '[<>\x01-\x1f\x7f-\x9f ­؜᠎​-‏ -‮⁠-⁤⁦-⁯﻿]'
    AND lower(heard) <> lower(meant)
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS company_alias_one_active ON company_alias (tenant_id, company_id, lower(heard)) WHERE retired_at IS NULL;
COMMENT ON TABLE company_alias IS 'A speech correction learnt in one company (ADR 0014): a name the recogniser heard and the label a person meant, captured when a person fixes a misheard name (an approved rename of a concept born from speech within 24 hours, or a correction whose re-taught label is close in spelling or sound to the rejected one). Active aliases feed the teach prompt as data and head the Azure AI Speech phrase list (ADR 0013). An alias whose concept is deleted is retired; a reset, the company or the user removes rows at once; retired aliases are purged 30 days after retired_at. At most 1,000 active aliases per company.';
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0007 is one-way")
