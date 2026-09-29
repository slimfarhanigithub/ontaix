"""Content entry: proposal origin, document imports; the scripted-story columns go.

Brings a database created by revision 0001 from the earlier schema contract to the current
`contracts/schema.sql`: drops `tenant_settings.demo_story` and `tenant_view_state.scene_idx`,
adds the `proposal_origin` type, `proposal.origin` and `origin_detail` with their CHECKs,
`audit_entry.origin` with its CHECK, and the `document_import` and `document_import_sentence`
tables with their index. Every statement is idempotent, so on a database revision 0001 already
created from the current contract this revision changes nothing. The DDL of the new objects is
the contract's text, so constraint names and definitions match a database loaded from it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'proposal_origin' AND n.nspname = 'ontaix'
  ) THEN
    CREATE TYPE proposal_origin AS ENUM ('text', 'speech', 'document');
  END IF;
END
$$;

ALTER TABLE tenant_settings DROP COLUMN IF EXISTS demo_story;
ALTER TABLE tenant_view_state DROP COLUMN IF EXISTS scene_idx;
COMMENT ON TABLE tenant_settings IS 'The 22 tenant settings plus appearance and the connector egress allowlist; the two locked settings are enforced by CHECK constraints.';
COMMENT ON TABLE tenant_view_state IS 'Shared canvas state that survives reload: the coverage flag.';

CREATE TABLE IF NOT EXISTS document_import (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_kind       actor_kind NOT NULL,
  actor_user_id    uuid,
  actor_agent_id   uuid,
  file_name        text NOT NULL,
  media_type       text NOT NULL,
  sha256           bytea NOT NULL,
  sentence_count   integer NOT NULL,
  extracted_chars  integer NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz NOT NULL DEFAULT now() + interval '1 hour',
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, actor_agent_id) REFERENCES agent(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT document_import_actor_matches_kind CHECK (
    (actor_kind = 'user'  AND actor_user_id IS NOT NULL AND actor_agent_id IS NULL) OR
    (actor_kind = 'agent' AND actor_agent_id IS NOT NULL AND actor_user_id IS NULL)
  ),
  CONSTRAINT document_import_file_name CHECK (
    char_length(file_name) BETWEEN 1 AND 255
    AND octet_length(file_name) <= 1020
    AND file_name !~ '[/\\:\x01-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u061c\u2066-\u2069\ufeff]'
  ),
  CONSTRAINT document_import_media_type CHECK (media_type IN (
    'text/plain', 'text/markdown', 'text/csv', 'application/json',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf')),
  CONSTRAINT document_import_sha256 CHECK (octet_length(sha256) = 32),
  CONSTRAINT document_import_limits CHECK (sentence_count BETWEEN 0 AND 2000 AND extracted_chars BETWEEN 0 AND 2000000),
  CONSTRAINT document_import_one_hour CHECK (expires_at = created_at + interval '1 hour')
);
COMMENT ON TABLE document_import IS 'One uploaded document after server-side extraction: usable for one hour by the actor that created it, in its tenant. A purge every 15 minutes deletes imports whose expires_at is more than 24 hours old (their sentences cascade). Proposals copy the file name, media type, sentence index and position into proposal.origin_detail, so they survive the purge.';
CREATE INDEX IF NOT EXISTS document_import_by_expiry ON document_import (expires_at);

CREATE TABLE IF NOT EXISTS document_import_sentence (
  tenant_id       uuid NOT NULL,
  import_id       uuid NOT NULL,
  sentence_index  integer NOT NULL CHECK (sentence_index BETWEEN 0 AND 1999),
  text            text NOT NULL CHECK (char_length(text) BETWEEN 13 AND 399),
  position_unit   text CHECK (position_unit IN ('page', 'paragraph')),
  position_index  integer CHECK (position_index BETWEEN 1 AND 100000),
  parse_count     smallint NOT NULL DEFAULT 0 CHECK (parse_count BETWEEN 0 AND 3),
  drafted_at      timestamptz,
  PRIMARY KEY (tenant_id, import_id, sentence_index),
  FOREIGN KEY (tenant_id, import_id) REFERENCES document_import(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT document_import_sentence_position_pair CHECK ((position_unit IS NULL) = (position_index IS NULL))
);
COMMENT ON TABLE document_import_sentence IS 'Extracted sentences of an import in document order. parse_count caps teach parses per sentence at 3 and drafted_at marks the one proposal call allowed to cite the sentence; both are claimed with a conditional UPDATE ... RETURNING inside the calling transaction, and zero rows returned means the claim failed.';

ALTER TABLE proposal ADD COLUMN IF NOT EXISTS origin proposal_origin NOT NULL DEFAULT 'text';
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS origin_detail jsonb;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'proposal_origin_detail_iff_document' AND conrelid = 'ontaix.proposal'::regclass
  ) THEN
    ALTER TABLE proposal ADD CONSTRAINT proposal_origin_detail_iff_document CHECK ((origin = 'document') = (origin_detail IS NOT NULL));
  END IF;
END
$$;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'proposal_origin_detail_shape' AND conrelid = 'ontaix.proposal'::regclass
  ) THEN
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
    AND (origin_detail ->> 'fileName') !~ '[/\\:\x01-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u061c\u2066-\u2069\ufeff]'
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
  END IF;
END
$$;

ALTER TABLE audit_entry ADD COLUMN IF NOT EXISTS origin proposal_origin;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'audit_entry_origin_only_for_proposal' AND conrelid = 'ontaix.audit_entry'::regclass
  ) THEN
    ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_origin_only_for_proposal CHECK (origin IS NULL OR proposal_id IS NOT NULL);
  END IF;
END
$$;
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0002 removes the scripted-story columns and is one-way")
