"""Import formats, OCR, ontology import, concept expansion and whole-document extraction.

Brings a database of revision 0003 to the current `contracts/schema.sql`: the origins
`suggestion` and `ontology_import`; `tenant_settings.ocr_monthly_page_cap`; the new purposes,
outcome, latency bound and `pages` column of `llm_call`; `llm_month_usage.ocr_pages`; the
`expand`, `extraction` and `ocr` budgets; `document_import.ocr_pages` and the new media types;
the `slide` and `sheet` positions and `document_import_sentence.position_row`; the
`concept_expansion`, `document_extraction_job` and `ontology_import` tables; the redefined
`proposal_origin_detail_shape`; and `outbox.recipient_user_id` with its two CHECKs; with the
comments that describe them. Every statement is idempotent, so on a database revision 0001
already created from the current contract this revision changes nothing. The DDL is the
contract's text, so constraint names and definitions match a database loaded from it.

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

ALTER TYPE proposal_origin ADD VALUE IF NOT EXISTS 'suggestion';
ALTER TYPE proposal_origin ADD VALUE IF NOT EXISTS 'ontology_import';

ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS ocr_monthly_page_cap integer NOT NULL DEFAULT 1000 CHECK (ocr_monthly_page_cap BETWEEN 0 AND 1000000);
COMMENT ON TABLE tenant_settings IS 'The 22 tenant settings plus appearance, the connector egress allowlist and the monthly token cap of Ontaix''s own language model calls (default 2,000,000, so the teach extraction model step is on; 0 turns it off and is how an administrator opts out) and the monthly OCR page cap (default 1,000 pages; 0 turns OCR of scanned pages off); the two locked settings are enforced by CHECK constraints.';

ALTER TABLE llm_call DROP CONSTRAINT IF EXISTS llm_call_purpose_check;
ALTER TABLE llm_call ADD CONSTRAINT llm_call_purpose_check CHECK (purpose IN ('teach_extraction', 'concept_expansion', 'document_extraction', 'document_ocr'));
ALTER TABLE llm_call DROP CONSTRAINT IF EXISTS llm_call_latency_ms_check;
ALTER TABLE llm_call ADD CONSTRAINT llm_call_latency_ms_check CHECK (latency_ms BETWEEN 0 AND 300000);
ALTER TABLE llm_call ADD COLUMN IF NOT EXISTS pages integer CHECK (pages BETWEEN 0 AND 2000);
ALTER TABLE llm_call DROP CONSTRAINT IF EXISTS llm_call_pages_only_for_ocr;
ALTER TABLE llm_call ADD CONSTRAINT llm_call_pages_only_for_ocr CHECK ((purpose = 'document_ocr') = (pages IS NOT NULL));
ALTER TABLE llm_call DROP CONSTRAINT IF EXISTS llm_call_outcome_check;
ALTER TABLE llm_call ADD CONSTRAINT llm_call_outcome_check CHECK (outcome IN ('used', 'invalid_output', 'timeout', 'provider_error', 'refused'));
ALTER TABLE llm_call DROP CONSTRAINT IF EXISTS llm_call_refused_not_for_teach;
ALTER TABLE llm_call ADD CONSTRAINT llm_call_refused_not_for_teach CHECK (outcome <> 'refused' OR purpose <> 'teach_extraction');
COMMENT ON TABLE llm_call IS 'One cost record per call Ontaix makes to a language model provider, including failed and timed-out calls: who caused it (actor_id and company_id are plain uuids so the record survives the actor or company), why (purpose: teach_extraction, concept_expansion, document_extraction or document_ocr; an OCR call is priced per page, records pages, and its token counts are what the provider reports, often 0), which provider and model, token counts, the estimated euro cost from the deployment price table, latency and outcome. It never holds the sentence, the prompt, the answer or any credential. Cost management sums it per month; a purge deletes rows older than 400 days across all tenants through llm_call_by_occurred. It is inserted in its own short transaction after the call, never inside the request transaction.';

ALTER TABLE llm_month_usage ADD COLUMN IF NOT EXISTS ocr_pages  integer NOT NULL DEFAULT 0 CHECK (ocr_pages >= 0);
COMMENT ON TABLE llm_month_usage IS 'Tokens counted against tenant_settings.llm_monthly_token_cap per calendar month (UTC). Before a call the API reserves its upper bound (estimated input plus the maximum output tokens) with INSERT ... SELECT $reserve WHERE $reserve <= $cap ON CONFLICT (tenant_id, month) DO UPDATE SET tokens = llm_month_usage.tokens + EXCLUDED.tokens WHERE llm_month_usage.tokens + EXCLUDED.tokens <= $cap RETURNING tokens; zero rows returned means the cap is reached and the model step is skipped. The reservation commits in its own short transaction before the provider is called, never inside the request transaction, so no row lock is held during the call. After the call, in another short transaction, it settles with UPDATE ... SET tokens = greatest(tokens + $actual - $reserved, 0) WHERE tenant_id = $tenant AND month = $reserved_month, always the month the reservation was made in, even when the call ends in the next month. A call that times out or fails settles its actual count (0 when the provider reports none), which releases the rest of the reservation. A reservation whose process dies before settling stays counted until the month ends. ocr_pages counts OCR pages against tenant_settings.ocr_monthly_page_cap the same way: before an OCR call the API reserves the image-only page count with INSERT ... SELECT $pages WHERE $pages <= $page_cap ON CONFLICT (tenant_id, month) DO UPDATE SET ocr_pages = llm_month_usage.ocr_pages + EXCLUDED.ocr_pages WHERE llm_month_usage.ocr_pages + EXCLUDED.ocr_pages <= $page_cap RETURNING ocr_pages in its own short transaction, zero rows refusing the import with 503 unavailable, and settles to the pages the provider processed after the call. Users and agents draw on the same caps. Shared by every API replica.';

ALTER TABLE rate_budget_window DROP CONSTRAINT IF EXISTS rate_budget_window_budget_check;
ALTER TABLE rate_budget_window ADD CONSTRAINT rate_budget_window_budget_check CHECK (budget IN ('import', 'parse', 'proposal', 'llm', 'expand', 'extraction', 'ocr'));
COMMENT ON TABLE rate_budget_window IS 'Units spent per user or agent, per budget, per clock hour (window_start is a whole UTC hour), shared by every API replica. A charge of $n against $limit is one statement: INSERT INTO rate_budget_window (tenant_id, actor_kind, actor_id, budget, window_start, spent) SELECT $tenant, $kind, $actor, $budget, $window, $n WHERE $n <= $limit ON CONFLICT (tenant_id, actor_kind, actor_id, budget, window_start) DO UPDATE SET spent = rate_budget_window.spent + EXCLUDED.spent WHERE rate_budget_window.spent + EXCLUDED.spent <= $limit RETURNING spent; zero rows returned means the budget is exhausted and the call is refused (429 rate_limited, or llmOutcome rate_limited for the llm budget). The expand budget counts POST /concepts/{conceptId}/expand calls and is charged before the llm budget. The extraction budget counts whole-document extraction jobs started (POST /import/{importId}/extraction); the model calls of a job are bounded by its own token ceiling and the tenant cap, not by the per-call llm budget. The ocr budget counts OCR pages, charged for every image-only page before the OCR call. actor_id is a plain uuid so a charge never waits on a foreign key lock. A purge every 15 minutes deletes windows that started more than 2 hours ago.';

ALTER TABLE document_import ADD COLUMN IF NOT EXISTS ocr_pages        integer NOT NULL DEFAULT 0;
ALTER TABLE document_import DROP CONSTRAINT IF EXISTS document_import_ocr_pages;
ALTER TABLE document_import ADD CONSTRAINT document_import_ocr_pages CHECK (ocr_pages BETWEEN 0 AND 2000 AND (ocr_pages = 0 OR media_type = 'application/pdf'));
ALTER TABLE document_import DROP CONSTRAINT IF EXISTS document_import_media_type;
ALTER TABLE document_import ADD CONSTRAINT document_import_media_type CHECK (media_type IN (
    'text/plain', 'text/markdown', 'text/csv', 'application/json',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/html'));
COMMENT ON TABLE document_import IS 'One uploaded document after server-side extraction: usable for one hour by the actor that created it, in its tenant. media_type is the type the server sniffed from the bytes (ADR 0011), never the client header alone; ocr_pages counts the image-only PDF pages whose text came from OCR. A purge every 15 minutes deletes imports whose expires_at is more than 24 hours old (their sentences cascade). Proposals copy the file name, media type, sentence index and position into proposal.origin_detail, so they survive the purge.';

ALTER TABLE document_import_sentence DROP CONSTRAINT IF EXISTS document_import_sentence_position_unit_check;
ALTER TABLE document_import_sentence ADD CONSTRAINT document_import_sentence_position_unit_check CHECK (position_unit IN ('page', 'paragraph', 'slide', 'sheet'));
ALTER TABLE document_import_sentence ADD COLUMN IF NOT EXISTS position_row    integer CHECK (position_row BETWEEN 1 AND 1048576);
ALTER TABLE document_import_sentence DROP CONSTRAINT IF EXISTS document_import_sentence_row_only_for_sheet;
ALTER TABLE document_import_sentence ADD CONSTRAINT document_import_sentence_row_only_for_sheet CHECK (position_row IS NULL OR position_unit IS NOT DISTINCT FROM 'sheet');

CREATE TABLE IF NOT EXISTS concept_expansion (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_user_id   uuid NOT NULL,
  company_id      uuid NOT NULL,
  concept_id      uuid NOT NULL,
  session_id      uuid,
  depth           integer CHECK (depth >= 1),
  max_children    integer CHECK (max_children >= 1),
  draft_count     integer NOT NULL CHECK (draft_count BETWEEN 1 AND 2000),
  drafts          jsonb NOT NULL,
  notes           jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL DEFAULT now() + interval '1 hour',
  submitted_at    timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, concept_id) REFERENCES concept(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT concept_expansion_drafts_shape CHECK (
    jsonb_typeof(drafts) = 'array'
    AND jsonb_array_length(drafts) = draft_count
    AND jsonb_typeof(notes) = 'array'
    AND jsonb_array_length(notes) = draft_count
    AND octet_length(drafts::text) + octet_length(notes::text) <= 4194304
  ),
  CONSTRAINT concept_expansion_one_hour CHECK (expires_at = created_at + interval '1 hour'),
  CONSTRAINT concept_expansion_submitted_in_time CHECK (submitted_at IS NULL OR submitted_at <= expires_at)
);
CREATE INDEX IF NOT EXISTS concept_expansion_by_expiry ON concept_expansion (expires_at);
COMMENT ON TABLE concept_expansion IS 'One set of model suggestions returned by POST /concepts/{conceptId}/expand, kept so that the proposals created from it are attested by the server as origin suggestion and hold exactly what the model suggested and the API validated. Written only when at least one draft survived validation; it is not an ontology row and holds no prompt, no answer text beyond the validated drafts and notes (labels, actions, confidence, one-line rationale), and no credential. Usable for one hour by the user that created it, in its tenant (users only: agents cannot expand). submitted_at marks the one successful POST /expansions/{expansionId}/proposals call, claimed with UPDATE concept_expansion SET submitted_at = now() WHERE <key> AND submitted_at IS NULL AND expires_at > now() RETURNING id inside the calling transaction; zero rows returned means the claim failed (409 expansion_submitted or 410 expansion_expired). A purge every 15 minutes deletes expansions whose expires_at is more than 24 hours old.';

CREATE TABLE IF NOT EXISTS document_extraction_job (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_user_id        uuid NOT NULL,
  import_id            uuid,
  company_id           uuid NOT NULL,
  state                text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  phase                text CHECK (phase IN ('outline', 'sections', 'mapping')),
  chunks               integer NOT NULL DEFAULT 0 CHECK (chunks >= 0),
  outline_chunks_done  integer NOT NULL DEFAULT 0 CHECK (outline_chunks_done BETWEEN 0 AND chunks),
  section_chunks_done  integer NOT NULL DEFAULT 0 CHECK (section_chunks_done BETWEEN 0 AND chunks),
  token_ceiling        integer NOT NULL CHECK (token_ceiling >= 1),
  node_ceiling         integer NOT NULL CHECK (node_ceiling BETWEEN 1 AND 5000),
  tokens_used          bigint NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
  outline              jsonb NOT NULL DEFAULT '[]'::jsonb,
  drafts               jsonb,
  notes                jsonb,
  unresolved           jsonb NOT NULL DEFAULT '[]'::jsonb,
  draft_count          integer NOT NULL DEFAULT 0 CHECK (draft_count BETWEEN 0 AND node_ceiling),
  degraded             boolean NOT NULL DEFAULT false,
  failure_reason       text CHECK (failure_reason IN ('not_configured', 'budget_exhausted', 'rate_limited', 'job_timeout', 'no_drafts', 'import_expired', 'too_many_attempts', 'internal')),
  cancel_requested     boolean NOT NULL DEFAULT false,
  lease_owner          uuid,
  lease_epoch          integer NOT NULL DEFAULT 0 CHECK (lease_epoch >= 0),
  lease_until          timestamptz,
  attempts             smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
  created_at           timestamptz NOT NULL DEFAULT now(),
  started_at           timestamptz,
  finished_at          timestamptz,
  expires_at           timestamptz,
  submitted_at         timestamptz,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, import_id),
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, import_id) REFERENCES document_import(tenant_id, id) ON DELETE SET NULL (import_id),
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT document_extraction_job_lease_pair CHECK ((lease_owner IS NULL) = (lease_until IS NULL)),
  CONSTRAINT document_extraction_job_no_lease_when_final CHECK (state IN ('queued', 'running') OR lease_owner IS NULL),
  CONSTRAINT document_extraction_job_phase_when_running CHECK ((state = 'running') = (phase IS NOT NULL)),
  CONSTRAINT document_extraction_job_failure_iff_failed CHECK ((state = 'failed') = (failure_reason IS NOT NULL)),
  CONSTRAINT document_extraction_job_finished_when_final CHECK ((state IN ('succeeded', 'failed', 'cancelled')) = (finished_at IS NOT NULL)),
  CONSTRAINT document_extraction_job_result_iff_succeeded CHECK (
    (state = 'succeeded') = (drafts IS NOT NULL)
    AND (drafts IS NULL) = (notes IS NULL)
    AND (drafts IS NULL) = (expires_at IS NULL)
  ),
  CONSTRAINT document_extraction_job_result_shape CHECK (
    drafts IS NULL OR COALESCE((
      jsonb_typeof(drafts) = 'array'
      AND jsonb_typeof(notes) = 'array'
      AND jsonb_array_length(drafts) = draft_count
      AND jsonb_array_length(notes) = draft_count
      AND draft_count >= 1
    ), false)
  ),
  CONSTRAINT document_extraction_job_arrays CHECK (jsonb_typeof(outline) = 'array' AND jsonb_typeof(unresolved) = 'array'),
  CONSTRAINT document_extraction_job_size CHECK (
    octet_length(outline::text) + octet_length(unresolved::text)
      + coalesce(octet_length(drafts::text), 0) + coalesce(octet_length(notes::text), 0) <= 16777216
  ),
  CONSTRAINT document_extraction_job_expiry CHECK (expires_at IS NULL OR expires_at = finished_at + interval '24 hours'),
  CONSTRAINT document_extraction_job_submitted_after_success CHECK (submitted_at IS NULL OR (state = 'succeeded' AND submitted_at <= expires_at))
);
CREATE UNIQUE INDEX IF NOT EXISTS document_extraction_job_one_running_per_user ON document_extraction_job (tenant_id, actor_user_id) WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS document_extraction_job_queue ON document_extraction_job (created_at) WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS document_extraction_job_by_expiry ON document_extraction_job (expires_at) WHERE expires_at IS NOT NULL;
COMMENT ON TABLE document_extraction_job IS 'One whole-document extraction job (POST /import/{importId}/extraction): two model passes over the chunked import, outline then sections, mapped by the server to one draft tree for company_id. At most one job per import (unique tenant_id, import_id) and one queued or running job per user (partial unique index). The runner in apps/api claims work with SELECT ... FROM document_extraction_job WHERE state IN (''queued'', ''running'') AND (lease_until IS NULL OR lease_until < now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1, then in the same transaction UPDATE ... SET lease_owner = $runner, lease_epoch = lease_epoch + 1, lease_until = now() + interval ''5 minutes'', attempts = attempts + 1 RETURNING lease_epoch; a job whose attempts would pass the configured limit (ONTAIX_DOCUMENT_EXTRACTION_MAX_ATTEMPTS, default 3) is instead set failed with failure_reason too_many_attempts. Fencing: every later write by that runner - lease renewal (after every chunk, during every model call''s wait at most every 60 seconds, and during mapping), progress, outline, token count, final state - is UPDATE ... WHERE id = $job AND lease_owner = $runner AND lease_epoch = $epoch AND lease_until > clock_timestamp() (the statement time, not the transaction start), in a short transaction; zero rows means the lease is lost, and the runner abandons the job at once without writing, settling only its own llm_month_usage reservation. The outbox row is written in the same fenced transaction. A job whose runner dies is picked up again and resumes at the next unfinished chunk. Progress, the outline and the settled token count are written after every chunk in a short transaction that also writes the extraction.changed outbox row; no transaction is open during a model call. Token reservation and settlement use llm_month_usage exactly as teach extraction; tokens_used stops the job at token_ceiling. drafts and notes hold the validated tree, each note carrying the grounding sentence index and the originDetail copied from the import, so proposals survive the import purge (import_id is set null by it). submitted_at marks the one successful POST /extractions/{extractionId}/proposals call, claimed with UPDATE ... WHERE submitted_at IS NULL AND state = ''succeeded'' AND expires_at > now() RETURNING id. It never holds a prompt, a raw model answer or a credential. A purge every 15 minutes deletes jobs whose expires_at is more than 24 hours old, and failed or cancelled jobs 48 hours after finished_at.';

CREATE TABLE IF NOT EXISTS ontology_import (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_kind         actor_kind NOT NULL,
  actor_user_id      uuid,
  actor_agent_id     uuid,
  company_id         uuid NOT NULL,
  parent_concept_id  uuid,
  file_name          text NOT NULL,
  format             text NOT NULL CHECK (format IN ('rdf_xml', 'turtle', 'owl_xml', 'json_ld', 'n_triples', 'obo', 'csv', 'xlsx')),
  sha256             bytea NOT NULL CHECK (octet_length(sha256) = 32),
  languages          text[] NOT NULL DEFAULT '{}',
  individuals        text NOT NULL DEFAULT 'skip' CHECK (individuals IN ('skip', 'as_concepts')),
  draft_count        integer NOT NULL CHECK (draft_count BETWEEN 0 AND 20000),
  drafts             jsonb NOT NULL,
  notes              jsonb NOT NULL,
  skipped            jsonb NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL DEFAULT now() + interval '24 hours',
  submitted_at       timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, actor_user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, actor_agent_id) REFERENCES agent(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, company_id) REFERENCES company(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, parent_concept_id) REFERENCES concept(tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT ontology_import_actor_matches_kind CHECK (
    (actor_kind = 'user'  AND actor_user_id IS NOT NULL AND actor_agent_id IS NULL) OR
    (actor_kind = 'agent' AND actor_agent_id IS NOT NULL AND actor_user_id IS NULL)
  ),
  CONSTRAINT ontology_import_file_name CHECK (
    char_length(file_name) BETWEEN 1 AND 255
    AND octet_length(file_name) <= 1020
    AND file_name !~ '[/\\:\x01-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u061c\u2066-\u2069\ufeff]'
  ),
  CONSTRAINT ontology_import_languages CHECK (
    cardinality(languages) <= 10 AND array_position(languages, NULL) IS NULL
    AND array_to_string(languages, ',') ~ '^([A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*(,[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*)*)?$'
    AND coalesce(array_length(string_to_array(array_to_string(languages, ','), ','), 1), 0) = cardinality(languages)
  ),
  CONSTRAINT ontology_import_result_shape CHECK (
    jsonb_typeof(drafts) = 'array' AND jsonb_array_length(drafts) = draft_count
    AND jsonb_typeof(notes) = 'array' AND jsonb_array_length(notes) = draft_count
    AND jsonb_typeof(skipped) = 'array'
    AND octet_length(drafts::text) + octet_length(notes::text) + octet_length(skipped::text) <= 67108864
  ),
  CONSTRAINT ontology_import_one_day CHECK (expires_at = created_at + interval '24 hours'),
  CONSTRAINT ontology_import_submitted_in_time CHECK (submitted_at IS NULL OR (draft_count >= 1 AND submitted_at <= expires_at))
);
CREATE INDEX IF NOT EXISTS ontology_import_by_expiry ON ontology_import (expires_at);
COMMENT ON TABLE ontology_import IS 'One uploaded ontology or hierarchy file (POST /ontology-imports) after deterministic mapping (ADR 0012): the draft tree for company_id under parent_concept_id (the company root when null), one note per draft (source IRI or row, chosen label and language, depth, requires) and the skipped items with their reasons. No language model is involved. The file itself is not kept, only its name, detected format and SHA-256. Usable for 24 hours by the actor that created it, in its tenant; submitted_at marks the one successful POST /ontology-imports/{ontologyImportId}/proposals call, claimed with UPDATE ... WHERE submitted_at IS NULL AND expires_at > now() RETURNING id inside the calling transaction. A purge every 15 minutes deletes rows whose expires_at is more than 24 hours old.';

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
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/html')
      AND jsonb_typeof(origin_detail -> 'sentenceIndex') = 'number'
      AND (origin_detail ->> 'sentenceIndex') ~ '^[0-9]{1,4}$'
      AND (origin_detail ->> 'sentenceIndex')::integer <= 1999
      AND (NOT (origin_detail ? 'position') OR (
        jsonb_typeof(origin_detail -> 'position') = 'object'
        AND ((origin_detail -> 'position') - 'unit' - 'index' - 'row') = '{}'::jsonb
        AND (origin_detail -> 'position' ->> 'unit') IN ('page', 'paragraph', 'slide', 'sheet')
        AND jsonb_typeof(origin_detail -> 'position' -> 'index') = 'number'
        AND (origin_detail -> 'position' ->> 'index') ~ '^[0-9]{1,6}$'
        AND (origin_detail -> 'position' ->> 'index')::integer BETWEEN 1 AND 100000
        AND (NOT ((origin_detail -> 'position') ? 'row') OR (
          (origin_detail -> 'position' ->> 'unit') = 'sheet'
          AND jsonb_typeof(origin_detail -> 'position' -> 'row') = 'number'
          AND (origin_detail -> 'position' ->> 'row') ~ '^[0-9]{1,7}$'
          AND (origin_detail -> 'position' ->> 'row')::integer BETWEEN 1 AND 1048576
        ))
      ))
    ), false)
  );

ALTER TABLE outbox ADD COLUMN IF NOT EXISTS recipient_user_id uuid;
ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_recipient_iff_extraction;
ALTER TABLE outbox ADD CONSTRAINT outbox_recipient_iff_extraction CHECK ((aggregate = 'extraction') = (recipient_user_id IS NOT NULL));
ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_extraction_shape;
ALTER TABLE outbox ADD CONSTRAINT outbox_extraction_shape CHECK (aggregate <> 'extraction' OR (visibility = 'model.read' AND cardinality(company_ids) = 1));
COMMENT ON TABLE outbox IS 'Events written in the same transaction as the state change they describe, with the permission and the company audience that make each visible; the relay publishes them to NATS in id order. recipient_user_id is set exactly on extraction events, whose audience is the one user who started the job (header Ontaix-Recipient); the writer takes it from document_extraction_job.actor_user_id, never from a request; it is a plain uuid with no foreign key. An extraction event is always model.read with exactly one company, the job''s. The hub and the ?since= replay deliver a row with a recipient only to that user.';
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` and backslashes stay."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0004 is one-way")
