"""Ontology editing, tenant domains, company creation setting, and the `export` budget.

Brings a database of revision 0008 to the current `contracts/schema.sql`: the change kinds
`create_domain`, `edit_domain`, `delete_domain`, `move_concept_domain` and `delete_bulk`;
`tenant_settings.company_creation`; the `tenant_domain` and `tenant_domain_revision` tables,
filled with the nine templates for every existing tenant (revision 0 each) before
`domain_product.template_key`, `group_role.scope_domain_key`, `agent.domain_key`,
`audit_entry.domain_key` and `outbox.domain_key` move their foreign keys from `domain_template`
to the composite `tenant_domain (tenant_id, key)`;
`proposal.revision` with its CHECKs; and the `export` budget of `rate_budget_window`. Every
statement is idempotent, so on a database revision 0001 already created from the current
contract this revision only copies the templates of tenants that lack them. The DDL is the
contract's text, so constraint names and definitions match a database loaded from it. The
label CHECKs are written with Python escapes for their control and format characters.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UPGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'create_domain';
ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'edit_domain';
ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'delete_domain';
ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'move_concept_domain';
ALTER TYPE change_kind ADD VALUE IF NOT EXISTS 'delete_bulk';

ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS company_creation boolean NOT NULL DEFAULT true;

COMMENT ON TABLE domain_template IS 'The nine fixed domain product templates every tenant starts from, in ring order. Each tenant copies them into tenant_domain when it is created, where they can be renamed; the templates themselves never change.';

CREATE TABLE IF NOT EXISTS tenant_domain (
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  key            text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{1,39}$'),
  name           text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)
                   AND name !~ '[<>\x01-\x1f\x7f-\x9f\xa0\xad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u206f\ufeff]'),
  owner          text NOT NULL DEFAULT '' CHECK (char_length(owner) <= 60
                   AND owner !~ '[<>\x01-\x1f\x7f-\x9f\xa0\xad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u206f\ufeff]'),
  default_color  text NOT NULL CHECK (default_color ~ '^#[0-9a-f]{6}$'),
  template_key   text REFERENCES domain_template(key),
  position       integer NOT NULL CHECK (position BETWEEN 0 AND 63),
  revision       integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
  created_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, key),
  UNIQUE (tenant_id, position),
  CONSTRAINT tenant_domain_template_keeps_key CHECK (template_key IS NULL OR template_key = key)
);
CREATE UNIQUE INDEX IF NOT EXISTS tenant_domain_name_unique ON tenant_domain (tenant_id, lower(name));
COMMENT ON TABLE tenant_domain IS 'The domains of one tenant (ADR 0015): the nine templates copied at tenant creation (template_key set) and custom domains created through an approved create_domain proposal (template_key null), at most 64. A domain is tenant-wide: its name, owner and colour are the same in every company, as the UI contract requires for colour. The effective colour is tenant_settings.colors[key] when set, else default_color; an approved edit_domain writes that override, exactly as Appearance does. revision counts approved edit_domain changes; tenant_domain_revision keeps each version. A domain is never deleted: delete_domain removes one company''s domain product and its concepts, and the domain stays available.';

CREATE TABLE IF NOT EXISTS tenant_domain_revision (
  tenant_id    uuid NOT NULL,
  key          text NOT NULL,
  revision     integer NOT NULL CHECK (revision >= 0),
  name         text NOT NULL,
  color        text NOT NULL CHECK (color ~ '^#[0-9a-f]{6}$'),
  owner        text NOT NULL,
  proposal_id  uuid,
  changed_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, key, revision),
  FOREIGN KEY (tenant_id, key) REFERENCES tenant_domain(tenant_id, key) ON DELETE CASCADE
);
COMMENT ON TABLE tenant_domain_revision IS 'Name, colour and owner of a tenant domain at each revision: revision 0 when the domain is created or copied from its template, one row per approved edit_domain (proposal_id set, a plain uuid so the history survives the proposal). A colour set immediately through Appearance is recorded in the audit log, not here.';

INSERT INTO tenant_domain (tenant_id, key, name, owner, default_color, template_key, position)
SELECT tenant.id, t.key, t.name, t.owner, t.color, t.key, t.position
FROM tenant CROSS JOIN domain_template t
ON CONFLICT DO NOTHING;
INSERT INTO tenant_domain_revision (tenant_id, key, revision, name, color, owner)
SELECT d.tenant_id, d.key, 0, d.name, d.default_color, d.owner
FROM tenant_domain d
ON CONFLICT DO NOTHING;

ALTER TABLE domain_product DROP CONSTRAINT IF EXISTS domain_product_template_key_fkey;
ALTER TABLE domain_product DROP CONSTRAINT IF EXISTS domain_product_tenant_id_template_key_fkey;
ALTER TABLE domain_product ADD CONSTRAINT domain_product_tenant_id_template_key_fkey FOREIGN KEY (tenant_id, template_key) REFERENCES tenant_domain(tenant_id, key) ON DELETE RESTRICT;
COMMENT ON TABLE domain_product IS 'One owned, versioned slice per company and tenant domain (template_key holds the tenant domain key, a template key or a custom one; a company''s product for a custom domain is created when its first concept joins it); revision increments by one on every approved change that carries the domain.';

ALTER TABLE group_role DROP CONSTRAINT IF EXISTS group_role_scope_domain_key_fkey;
ALTER TABLE group_role DROP CONSTRAINT IF EXISTS group_role_tenant_id_scope_domain_key_fkey;
ALTER TABLE group_role ADD CONSTRAINT group_role_tenant_id_scope_domain_key_fkey FOREIGN KEY (tenant_id, scope_domain_key) REFERENCES tenant_domain(tenant_id, key) ON DELETE CASCADE;
COMMENT ON TABLE group_role IS 'A role held by a group on one scope: the tenant, one company, or one domain (a tenant_domain key, a template or a custom domain, covering that domain product in every company); duplicates are refused. A role on a domain goes with the domain (CASCADE), never widening to another scope.';

ALTER TABLE agent DROP CONSTRAINT IF EXISTS agent_domain_key_fkey;
ALTER TABLE agent DROP CONSTRAINT IF EXISTS agent_tenant_id_domain_key_fkey;
ALTER TABLE agent ADD CONSTRAINT agent_tenant_id_domain_key_fkey FOREIGN KEY (tenant_id, domain_key) REFERENCES tenant_domain(tenant_id, key) ON DELETE RESTRICT;
COMMENT ON TABLE agent IS 'A machine identity from any platform: its token (issuer, subject) maps to this row; company_id null means tenant-wide scope; domain_key narrows it to one tenant domain and is RESTRICT, because clearing it would widen the agent''s scope; access can be switched off.';

ALTER TABLE audit_entry DROP CONSTRAINT IF EXISTS audit_entry_domain_key_fkey;
ALTER TABLE audit_entry DROP CONSTRAINT IF EXISTS audit_entry_tenant_id_domain_key_fkey;
ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_tenant_id_domain_key_fkey FOREIGN KEY (tenant_id, domain_key) REFERENCES tenant_domain(tenant_id, key) ON DELETE SET NULL (domain_key);
COMMENT ON COLUMN audit_entry.domain_key IS 'The tenant domain key (template or custom, same tenant through the composite foreign key; ON DELETE SET NULL, which the append-only trigger refuses, so a tenant domain still named by the log cannot be deleted - domains are never deleted in any case) of the domain product of the proposal the entry records, when that proposal has one; null for every other entry. A holder of audit.read on the domain scope with this key reads the entry whatever its company_ids, because that scope covers the domain product in every company and matches the proposals it may decide.';

ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_domain_key_fkey;
ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_tenant_id_domain_key_fkey;
ALTER TABLE outbox ADD CONSTRAINT outbox_tenant_id_domain_key_fkey FOREIGN KEY (tenant_id, domain_key) REFERENCES tenant_domain(tenant_id, key) ON DELETE SET NULL (domain_key);

ALTER TABLE rate_budget_window DROP CONSTRAINT IF EXISTS rate_budget_window_budget_check;
ALTER TABLE rate_budget_window ADD CONSTRAINT rate_budget_window_budget_check CHECK (budget IN ('import', 'parse', 'proposal', 'llm', 'expand', 'extraction', 'ocr', 'speech', 'export'));

ALTER TABLE proposal ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 0 CHECK (revision BETWEEN 0 AND 1000);
ALTER TABLE proposal DROP CONSTRAINT IF EXISTS proposal_revision_only_for_editable;
ALTER TABLE proposal ADD CONSTRAINT proposal_revision_only_for_editable CHECK (revision = 0 OR type IN ('concept', 'spec', 'relation'));
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` stays literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0009 is one-way")
