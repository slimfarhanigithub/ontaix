"""Organizations and sign-in: accounts, sessions, company mode and row-level security.

Brings a database of revision 0007 to the current `contracts/schema.sql`: the actor kind
`platform`; the enums of the sign-in tables; `tenant.disabled_at`, `tenant.updated_at`, the slug
and name checks and the case-insensitive unique name; `organization_settings`; `account`,
`password_credential`, `platform_role_assignment`, `auth_session`, `sign_in_throttle` and the
append-only `platform_audit_entry`; `audit_entry.actor_account_id` with its check;
`resolve_session()`; the company-mode triggers; the NOLOGIN roles `ontaix_app` and
`ontaix_platform`, row-level security on every `tenant_id` table and on `tenant`, and the grants.

Every existing tenant becomes an organization with `company_mode` `multiple`, its ids, data,
groups and audit log unchanged. No account, password or platform role is created: the owner
runs `python -m app.admin create-super-admin` once.

Every statement is idempotent, so on a database revision 0001 already created from the current
contract this revision changes nothing. The DDL is the contract's text, so constraint names and
definitions match a database loaded from it.

Revision ID: 0008
Revises: 0006
Create Date: 2026-09-30
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# A new enum value cannot be used in the transaction that adds it, so it commits on its own.
ENUM_DDL = "ALTER TYPE ontaix.actor_kind ADD VALUE IF NOT EXISTS 'platform'"

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'ontaix' AND t.typname = 'company_mode') THEN
    CREATE TYPE company_mode AS ENUM ('single', 'multiple');
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'ontaix' AND t.typname = 'platform_role_name') THEN
    CREATE TYPE platform_role_name AS ENUM ('super_admin');
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'ontaix' AND t.typname = 'password_set_reason') THEN
    CREATE TYPE password_set_reason AS ENUM ('bootstrap', 'initial', 'reset', 'change');
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'ontaix' AND t.typname = 'session_end_reason') THEN
    CREATE TYPE session_end_reason AS ENUM ('sign_out', 'password_changed', 'password_reset', 'account_disabled', 'organization_disabled', 'session_limit', 'support_changed');
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'ontaix' AND t.typname = 'throttle_key_kind') THEN
    CREATE TYPE throttle_key_kind AS ENUM ('email', 'ip');
  END IF;
END $$;

ALTER TABLE tenant ADD COLUMN IF NOT EXISTS disabled_at timestamptz;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE tenant DROP CONSTRAINT IF EXISTS tenant_slug_check;
ALTER TABLE tenant ADD CONSTRAINT tenant_slug_check CHECK (slug ~ '^[a-z0-9]([a-z0-9-]{0,46}[a-z0-9])?$');
ALTER TABLE tenant DROP CONSTRAINT IF EXISTS tenant_name_check;
ALTER TABLE tenant ADD CONSTRAINT tenant_name_check CHECK (char_length(name) BETWEEN 1 AND 120);
CREATE UNIQUE INDEX IF NOT EXISTS tenant_name_unique ON tenant (lower(name));
COMMENT ON TABLE tenant IS 'One organization (the API and the portal call a tenant an organization): its own instance, whose users see only its data; every other tenant-scoped row points at exactly one tenant. Created, renamed, disabled and enabled only by a super admin. A disabled organization keeps its data and nobody signs into it.';

CREATE TABLE IF NOT EXISTS organization_settings (
  tenant_id      uuid PRIMARY KEY REFERENCES tenant(id) ON DELETE CASCADE,
  company_mode   company_mode NOT NULL DEFAULT 'multiple',
  updated_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE organization_settings IS 'Settings only a super admin writes. company_mode single caps the organization at one company: a second company row is refused by trigger, and tenant_settings.multi_company stays false. The application role reads this table and never writes it.';

COMMENT ON TABLE app_user IS 'The native user directory of an organization. A user who signs in with a password has issuer ''local'' and the id of its account as subject, and is created with its account by a super admin; a user signing in through OIDC is provisioned on first sign-in into the tenant that owns the token issuer; the development seed''s users have issuer ''dev''. How a user authenticates never decides what the user may do.';

ALTER TABLE audit_entry ADD COLUMN IF NOT EXISTS actor_account_id uuid;
ALTER TABLE audit_entry DROP CONSTRAINT IF EXISTS audit_entry_platform_actor;
ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_platform_actor CHECK ((actor_kind = 'platform') = (actor_account_id IS NOT NULL));
COMMENT ON COLUMN audit_entry.actor_account_id IS 'Set exactly when actor_kind is platform: the super admin''s platform account, for the organization''s entries of kind platform (a user created, a password reset, a support session started or ended, the organization renamed, disabled or re-enabled, its company mode changed).';

-- ---------------------------------------------------------------------------
-- Sign-in: accounts, password credentials, platform roles, sessions, throttle
-- ---------------------------------------------------------------------------
-- These tables are platform-level: the application role (ontaix_app) holds no privilege on
-- them and reaches a session only through ontaix.resolve_session(). The platform role
-- (ontaix_platform) serves /auth/*, /admin/*, the admin CLI and the cross-tenant jobs.

CREATE TABLE IF NOT EXISTS account (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text NOT NULL CHECK (char_length(email) BETWEEN 3 AND 254 AND email = lower(email) AND email ~ '^[^@\s]+@[^@\s]+$'),
  name             text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
  tenant_id        uuid,
  user_id          uuid,
  is_platform      boolean GENERATED ALWAYS AS (tenant_id IS NULL) STORED,
  disabled_at      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  last_sign_in_at  timestamptz,
  UNIQUE (email),
  UNIQUE (id, is_platform),
  UNIQUE (user_id),
  CONSTRAINT account_member_or_platform CHECK ((tenant_id IS NULL) = (user_id IS NULL)),
  FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE
);
COMMENT ON TABLE account IS 'A sign-in identity. A member account belongs to exactly one organization and is linked one to one to its app_user row (issuer ''local'', subject the account id); a platform account (tenant_id null) belongs to no organization and holds platform roles. The email is stored lower-case and is unique across the deployment, so the sign-in page needs no organization field. Authentication only: what a member may do comes from the organization''s groups, what a platform account may do from platform_role_assignment.';

CREATE TABLE IF NOT EXISTS password_credential (
  account_id  uuid PRIMARY KEY REFERENCES account(id) ON DELETE CASCADE,
  hash        text NOT NULL CHECK (hash LIKE '$argon2id$v=19$%'),
  must_change boolean NOT NULL,
  set_reason  password_set_reason NOT NULL,
  set_at      timestamptz NOT NULL DEFAULT now(),
  set_by      uuid,
  CONSTRAINT password_credential_forced_change CHECK (must_change = (set_reason IN ('initial', 'reset')))
);
COMMENT ON TABLE password_credential IS 'The argon2id hash of an account''s password in PHC string form (parameters, salt and tag; never the password). A password another person set (initial or reset, by a super admin) must be changed at the next sign-in; one the holder set (change, or bootstrap through the local admin CLI) need not. An account without a row cannot sign in with a password.';

CREATE TABLE IF NOT EXISTS platform_role_assignment (
  account_id   uuid NOT NULL,
  is_platform  boolean NOT NULL DEFAULT true CHECK (is_platform),
  role         platform_role_name NOT NULL,
  granted_at   timestamptz NOT NULL DEFAULT now(),
  granted_by   uuid,
  PRIMARY KEY (account_id, role),
  FOREIGN KEY (account_id, is_platform) REFERENCES account(id, is_platform) ON DELETE CASCADE
);
COMMENT ON TABLE platform_role_assignment IS 'Platform roles, held only by platform accounts (the composite foreign key refuses a member account). super_admin creates, renames, disables and enables organizations, sets their company mode, creates their accounts, resets passwords and opens audited read-only support sessions; it grants nothing inside an organization outside a support session. Written only by the local admin CLI.';

CREATE TABLE IF NOT EXISTS auth_session (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash           bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  csrf_token           text NOT NULL CHECK (char_length(csrf_token) = 43),
  account_id           uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  support_tenant_id    uuid REFERENCES tenant(id) ON DELETE CASCADE,
  support_until        timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  last_seen_at         timestamptz NOT NULL DEFAULT now(),
  idle_expires_at      timestamptz NOT NULL,
  absolute_expires_at  timestamptz NOT NULL,
  ended_at             timestamptz,
  end_reason           session_end_reason,
  client_ip            inet,
  user_agent           text CHECK (char_length(user_agent) <= 256),
  CONSTRAINT auth_session_support_pair CHECK ((support_tenant_id IS NULL) = (support_until IS NULL)),
  CONSTRAINT auth_session_end_pair CHECK ((ended_at IS NULL) = (end_reason IS NULL)),
  CONSTRAINT auth_session_expiry_order CHECK (idle_expires_at <= absolute_expires_at AND created_at < absolute_expires_at)
);
CREATE INDEX IF NOT EXISTS auth_session_by_account ON auth_session (account_id) WHERE ended_at IS NULL;
COMMENT ON TABLE auth_session IS 'A server-side browser session. The cookie carries a 256-bit random token; only its SHA-256 is stored, so a database read never yields a usable cookie. A session is valid while ended_at is null, now() is before idle_expires_at (30 minutes, slid forward on use) and absolute_expires_at (12 hours after sign-in), the account is enabled and, for a member, the organization is enabled. Sign-in, a password change and the start or end of a support session each issue a new token and end the old row, so a token never survives a change of privilege. support_tenant_id is set only on a super admin''s session during an audited read-only support session in that organization, until support_until.';
COMMENT ON COLUMN auth_session.csrf_token IS 'The synchronizer token the Studio echoes in X-CSRF-Token on every unsafe request; returned only by sign-in, GET /auth/session and the calls that issue a new session token. It is useless without the session cookie, so it is stored as issued.';

CREATE TABLE IF NOT EXISTS sign_in_throttle (
  key_kind      throttle_key_kind NOT NULL,
  key_hash      bytea NOT NULL CHECK (octet_length(key_hash) = 32),
  failures      integer NOT NULL DEFAULT 0 CHECK (failures >= 0),
  window_start  timestamptz NOT NULL DEFAULT now(),
  locked_until  timestamptz,
  PRIMARY KEY (key_kind, key_hash)
);
COMMENT ON TABLE sign_in_throttle IS 'Failed sign-in counters keyed by the SHA-256 of the normalized email (whether or not an account has it, so a lock reveals nothing about which emails exist) and of the client IP. Five failures within 15 minutes lock that key for 15 minutes. A successful sign-in clears the email key; a super admin password reset clears the account''s email key. Neither the email nor the IP is stored in clear.';

CREATE TABLE IF NOT EXISTS platform_audit_entry (
  id                 bigserial PRIMARY KEY,
  at                 timestamptz NOT NULL DEFAULT now(),
  actor_account_id   uuid,
  action             text NOT NULL CHECK (action IN (
                       'sign_in', 'sign_in_failed', 'sign_in_locked', 'sign_out', 'session_expired',
                       'password_changed', 'password_change_failed', 'password_reset',
                       'account_created', 'account_updated', 'account_disabled', 'account_enabled',
                       'organization_created', 'organization_renamed', 'organization_company_mode',
                       'organization_disabled', 'organization_enabled',
                       'support_session_started', 'support_session_ended',
                       'super_admin_created', 'super_admin_password_set')),
  ok                 boolean NOT NULL,
  target_tenant_id   uuid,
  target_account_id  uuid,
  what               text NOT NULL,
  client_ip          inet
);
CREATE INDEX IF NOT EXISTS platform_audit_entry_by_time ON platform_audit_entry (at DESC);
CREATE INDEX IF NOT EXISTS platform_audit_entry_by_tenant ON platform_audit_entry (target_tenant_id, at DESC) WHERE target_tenant_id IS NOT NULL;
COMMENT ON TABLE platform_audit_entry IS 'Append-only log of every authentication event and every super admin action, read by super admins through GET /admin/audit. Ids are plain columns without foreign keys. what never holds a password, a token, a hash, or an email that matches no account. An event about a member of an organization, or performed inside one, is also written to that organization''s audit_entry (kinds auth and platform) in the same transaction.';

CREATE OR REPLACE TRIGGER platform_audit_entry_no_update_or_delete
  BEFORE UPDATE OR DELETE ON platform_audit_entry
  FOR EACH ROW EXECUTE FUNCTION audit_entry_is_append_only();

CREATE OR REPLACE TRIGGER platform_audit_entry_no_truncate
  BEFORE TRUNCATE ON platform_audit_entry
  FOR EACH STATEMENT EXECUTE FUNCTION audit_entry_is_append_only();

CREATE OR REPLACE FUNCTION resolve_session(p_token_hash bytea)
RETURNS TABLE (
  session_id            uuid,
  account_id            uuid,
  tenant_id             uuid,
  user_id               uuid,
  is_platform           boolean,
  support_tenant_id     uuid,
  must_change_password  boolean,
  csrf_token            text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ontaix, pg_catalog, pg_temp
AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  UPDATE ontaix.auth_session s
     SET last_seen_at = now(),
         idle_expires_at = least(now() + interval '30 minutes', s.absolute_expires_at)
    FROM ontaix.account a
    LEFT JOIN ontaix.tenant t ON t.id = a.tenant_id
    LEFT JOIN ontaix.password_credential pc ON pc.account_id = a.id
   WHERE s.token_hash = p_token_hash
     AND s.account_id = a.id
     AND s.ended_at IS NULL
     AND now() < s.idle_expires_at
     AND now() < s.absolute_expires_at
     AND a.disabled_at IS NULL
     AND (a.tenant_id IS NULL OR t.disabled_at IS NULL)
  RETURNING s.id, a.id, a.tenant_id, a.user_id, a.is_platform,
            CASE WHEN s.support_until > now() THEN s.support_tenant_id END,
            coalesce(pc.must_change, false), s.csrf_token;
END;
$$;
COMMENT ON FUNCTION resolve_session(bytea) IS 'The only way the application role reads a session: given the SHA-256 of a presented cookie token, returns the live session''s account, organization, user, platform flag, active support organization, forced-change flag and CSRF token, and slides the 30-minute idle expiry (never past the absolute expiry). Returns no row for an unknown, ended, expired or disabled session, account or organization. The caller then sets ontaix.tenant_id for the transaction; a session with must_change_password true may only read GET /auth/session, change its password and sign out.';

-- ---------------------------------------------------------------------------
-- Company mode
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION company_respects_company_mode() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ontaix, pg_catalog, pg_temp
AS $$
DECLARE
  mode ontaix.company_mode;
BEGIN
  -- Locking the settings row serialises company inserts and mode changes of one organization.
  SELECT os.company_mode INTO mode FROM ontaix.organization_settings os
   WHERE os.tenant_id = NEW.tenant_id FOR UPDATE;
  IF mode = 'single' AND EXISTS (SELECT 1 FROM ontaix.company c WHERE c.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'organization % is in single company mode', NEW.tenant_id
      USING ERRCODE = 'check_violation', CONSTRAINT = 'company_limit';
  END IF;
  RETURN NEW;
END;
$$;
COMMENT ON FUNCTION company_respects_company_mode() IS 'Refuses a second company in an organization whose company_mode is single; the API answers 409 company_limit before this fires.';

CREATE OR REPLACE TRIGGER company_limit
  BEFORE INSERT ON company
  FOR EACH ROW EXECUTE FUNCTION company_respects_company_mode();

CREATE OR REPLACE FUNCTION organization_company_mode_fits() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ontaix, pg_catalog, pg_temp
AS $$
BEGIN
  IF NEW.company_mode = 'single' THEN
    IF (SELECT count(*) FROM ontaix.company c WHERE c.tenant_id = NEW.tenant_id) > 1 THEN
      RAISE EXCEPTION 'organization % has more than one company', NEW.tenant_id
        USING ERRCODE = 'check_violation', CONSTRAINT = 'company_limit';
    END IF;
    UPDATE ontaix.tenant_settings SET multi_company = false, updated_at = now()
     WHERE tenant_id = NEW.tenant_id AND multi_company;
  END IF;
  RETURN NEW;
END;
$$;
COMMENT ON FUNCTION organization_company_mode_fits() IS 'Refuses single company mode while the organization has two or more companies, and turns the organization''s multiCompany setting off when single mode is set.';

CREATE OR REPLACE TRIGGER organization_company_mode_fits
  AFTER INSERT OR UPDATE OF company_mode ON organization_settings
  FOR EACH ROW EXECUTE FUNCTION organization_company_mode_fits();

CREATE OR REPLACE FUNCTION tenant_settings_multi_company_allowed() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ontaix, pg_catalog, pg_temp
AS $$
BEGIN
  IF NEW.multi_company AND EXISTS (
    SELECT 1 FROM ontaix.organization_settings os WHERE os.tenant_id = NEW.tenant_id AND os.company_mode = 'single'
  ) THEN
    RAISE EXCEPTION 'organization % is in single company mode', NEW.tenant_id
      USING ERRCODE = 'check_violation', CONSTRAINT = 'locked_setting';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER tenant_settings_multi_company_allowed
  BEFORE INSERT OR UPDATE OF multi_company ON tenant_settings
  FOR EACH ROW EXECUTE FUNCTION tenant_settings_multi_company_allowed();

-- ---------------------------------------------------------------------------
-- Tenant isolation: database roles, row-level security and grants
-- ---------------------------------------------------------------------------
-- Two NOLOGIN roles; each deployment grants one of them to the login it connects with.
--   ontaix_app       every organization-scoped request and job. Row-level security limits it to
--                    the organization named by the transaction setting ontaix.tenant_id; unset,
--                    it sees and writes no tenant row (fail closed).
--   ontaix_platform  /auth/*, /admin/*, the admin CLI, the outbox relay, the projector and the
--                    purge jobs: the only code that reads across organizations.
-- The schema owner runs migrations and is not granted to either login. Row-level security is
-- defence in depth under the repositories' own tenant_id filters, never a replacement for them.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ontaix_app') THEN
    CREATE ROLE ontaix_app NOLOGIN NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ontaix_platform') THEN
    CREATE ROLE ontaix_platform NOLOGIN NOBYPASSRLS;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = ontaix, pg_catalog, pg_temp
AS $$ SELECT nullif(current_setting('ontaix.tenant_id', true), '')::uuid $$;
COMMENT ON FUNCTION current_tenant_id() IS 'The organization of the current transaction, set with set_config(''ontaix.tenant_id'', <id>, true) right after the session is resolved; null when unset, which matches no row.';

DO $$
DECLARE
  t text;
BEGIN
  FOR t IN
    SELECT c.table_name
      FROM information_schema.columns c
      JOIN information_schema.tables tb
        ON tb.table_schema = c.table_schema AND tb.table_name = c.table_name
     WHERE c.table_schema = 'ontaix'
       AND c.column_name = 'tenant_id'
       AND tb.table_type = 'BASE TABLE'
       AND c.table_name NOT IN ('account')
  LOOP
    EXECUTE format('ALTER TABLE ontaix.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON ontaix.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS platform_access ON ontaix.%I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON ontaix.%I TO ontaix_app '
      'USING (tenant_id = ontaix.current_tenant_id()) WITH CHECK (tenant_id = ontaix.current_tenant_id())', t);
    EXECUTE format('CREATE POLICY platform_access ON ontaix.%I TO ontaix_platform USING (true) WITH CHECK (true)', t);
  END LOOP;
END;
$$;

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenant;
CREATE POLICY tenant_isolation ON tenant TO ontaix_app USING (id = current_tenant_id());
DROP POLICY IF EXISTS platform_access ON tenant;
CREATE POLICY platform_access ON tenant TO ontaix_platform USING (true) WITH CHECK (true);

GRANT USAGE ON SCHEMA ontaix TO ontaix_app, ontaix_platform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ontaix TO ontaix_app, ontaix_platform;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ontaix TO ontaix_app, ontaix_platform;
REVOKE UPDATE, DELETE ON audit_entry, platform_audit_entry FROM ontaix_app, ontaix_platform;
REVOKE ALL ON account, password_credential, platform_role_assignment, auth_session, sign_in_throttle, platform_audit_entry FROM ontaix_app;
REVOKE INSERT, UPDATE, DELETE ON tenant, organization_settings, domain_template, connector_type FROM ontaix_app;
REVOKE INSERT, UPDATE, DELETE ON platform_role_assignment, domain_template, connector_type FROM ontaix_platform;
REVOKE ALL ON FUNCTION resolve_session(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_session(bytea) TO ontaix_app, ontaix_platform;

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(c.relname, ', ') INTO missing
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
   WHERE n.nspname = 'ontaix' AND c.relkind = 'r' AND c.relname <> 'account' AND NOT c.relrowsecurity;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'tables with tenant_id but no row-level security: %', missing;
  END IF;
END;
$$;

INSERT INTO organization_settings (tenant_id) SELECT id FROM tenant ON CONFLICT (tenant_id) DO NOTHING;
"""


def upgrade() -> None:
    """Add the enum value in its own committed transaction, then run the DDL on the raw psycopg
    cursor with no parameters, so `%` and backslashes stay."""
    with op.get_context().autocommit_block():
        op.execute(ENUM_DDL)
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0008 is one-way")
