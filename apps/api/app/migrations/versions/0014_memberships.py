"""Memberships: an account belongs to organizations through `account_membership` rows.

Brings a database of revision 0013 to the current `contracts/schema.sql`: the session end reason
`membership_removed`; `account_membership` (one row per account and organization, linked to the
organization's directory user, with row-level security and platform-only privileges like the
other sign-in tables); `account.is_platform` as a stored boolean in place of the generated
column, and `account.tenant_id` and `account.user_id` dropped; `auth_session.tenant_id`, the
organization a member session is inside; `resolve_session()` reading the organization and the
directory user from the session's membership, and returning no row once that membership is
disabled or removed; the platform log actions `membership_added`, `membership_removed` and
`organization_chosen`; and the comments.

Every member account becomes one membership of its organization: the membership takes the
account's `disabled_at`, the directory user's subject becomes `<account id>:<tenant id>`, and
every live session of the account is placed inside that organization. Platform accounts keep
`is_platform` true and hold no membership. Every statement is idempotent, so on a database
revision 0001 already created from the current contract this revision changes nothing; the data
moves run only while `account.tenant_id` exists. The DDL is the contract's text, so constraint
names and definitions match a database loaded from it.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-23
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# A new enum value cannot be used in the transaction that adds it, so it commits on its own.
ENUM_DDL = "ALTER TYPE ontaix.session_end_reason ADD VALUE IF NOT EXISTS 'membership_removed'"

UPGRADE_DDL = r"""
SET search_path TO ontaix, public;

CREATE TABLE IF NOT EXISTS account_membership (
  account_id   uuid NOT NULL,
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  user_id      uuid NOT NULL,
  is_platform  boolean NOT NULL DEFAULT false CHECK (NOT is_platform),
  disabled_at  timestamptz,
  removed_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, tenant_id),
  UNIQUE (user_id),
  FOREIGN KEY (account_id, is_platform) REFERENCES account(id, is_platform) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, user_id) REFERENCES app_user(tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS account_membership_by_tenant ON account_membership (tenant_id) WHERE removed_at IS NULL;
COMMENT ON TABLE account_membership IS 'An account''s membership of one organization, through that organization''s directory user (app_user, issuer ''local'', subject ''<account id>:<tenant id>''). One row per account and organization; only member accounts hold one (the composite foreign key refuses a platform account). disabled_at disables the member in this organization alone. removed_at records a removal from the organization: a removed member is not listed, signs into no session of this organization and loses its groups, while the directory user and the row stay so that history keeps naming one user; adding the account again clears removed_at and keeps the same user. A membership is active while neither is set and the organization is enabled. Read only by the platform role, like every sign-in table; it carries tenant_id and so row-level security like every other such table.';

ALTER TABLE auth_session ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES tenant(id) ON DELETE CASCADE;

-- Each member account becomes a membership of its organization, before its columns go.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'ontaix' AND table_name = 'account' AND column_name = 'tenant_id'
  ) THEN
    EXECUTE $m$
      INSERT INTO ontaix.account_membership (account_id, tenant_id, user_id, disabled_at, created_at)
      SELECT a.id, a.tenant_id, a.user_id, a.disabled_at, a.created_at
        FROM ontaix.account a
       WHERE a.tenant_id IS NOT NULL AND a.user_id IS NOT NULL
      ON CONFLICT (account_id, tenant_id) DO NOTHING
    $m$;
    EXECUTE $m$
      UPDATE ontaix.app_user u
         SET subject = a.id::text || ':' || a.tenant_id::text
        FROM ontaix.account a
       WHERE a.tenant_id = u.tenant_id AND a.user_id = u.id
         AND u.issuer = 'local' AND u.subject = a.id::text
    $m$;
    EXECUTE $m$
      UPDATE ontaix.auth_session s
         SET tenant_id = a.tenant_id
        FROM ontaix.account a
       WHERE a.id = s.account_id AND a.tenant_id IS NOT NULL AND s.tenant_id IS NULL
    $m$;
    EXECUTE $m$
      UPDATE ontaix.account SET disabled_at = NULL WHERE tenant_id IS NOT NULL AND disabled_at IS NOT NULL
    $m$;
  END IF;
END;
$$;

ALTER TABLE account ALTER COLUMN is_platform DROP EXPRESSION IF EXISTS;
ALTER TABLE account ALTER COLUMN is_platform SET DEFAULT false;
ALTER TABLE account ALTER COLUMN is_platform SET NOT NULL;
ALTER TABLE account DROP CONSTRAINT IF EXISTS account_member_or_platform;
ALTER TABLE account DROP CONSTRAINT IF EXISTS account_tenant_id_user_id_fkey;
ALTER TABLE account DROP CONSTRAINT IF EXISTS account_tenant_id_fkey;
ALTER TABLE account DROP CONSTRAINT IF EXISTS account_user_id_key;
ALTER TABLE account DROP COLUMN IF EXISTS user_id;
ALTER TABLE account DROP COLUMN IF EXISTS tenant_id;
COMMENT ON TABLE account IS 'A sign-in identity: a person with one email and one password across the deployment. A member account (is_platform false) belongs to organizations through account_membership rows, one per organization, each linked to that organization''s app_user row; a platform account (is_platform true) belongs to no organization and holds platform roles. The email is stored lower-case and is unique across the deployment, so the sign-in page needs no organization field. disabled_at disables a platform account; a member is disabled per organization on its membership. Authentication only: what a member may do comes from the organization''s groups, what a platform account may do from platform_role_assignment.';

COMMENT ON TABLE app_user IS 'The native user directory of an organization. A user who signs in with a password has issuer ''local'' and subject ''<account id>:<tenant id>'', and is created by a super admin with the account''s membership of the organization (account_membership); one account is one such user in each of its organizations, and a removed member''s user stays so that its proposals, approvals and audit rows keep naming it. A user signing in through OIDC is provisioned on first sign-in into the tenant that owns the token issuer; the development seed''s users have issuer ''dev''. A super admin who enters the organization acts through a directory user with issuer ''platform'' and subject ''<account id>:<tenant id>'', created at the first entry, so that proposals, approvals and every other row he writes name a user of the organization; it belongs to no group and its roles come from the platform access alone. How a user authenticates never decides what the user may do.';
COMMENT ON TABLE auth_session IS 'A server-side browser session. The cookie carries a 256-bit random token; only its SHA-256 is stored, so a database read never yields a usable cookie. A session is valid while ended_at is null, now() is before idle_expires_at (30 minutes, slid forward on use) and absolute_expires_at (12 hours after sign-in), the account is enabled and, for a member session inside an organization, its membership of that organization is active and the organization enabled. tenant_id is the organization a member session is inside: set at sign-in when the account has exactly one active membership, otherwise null until the member chooses one (PUT /auth/session/organization, which issues a new token); always null on a platform account''s session. Sign-in, a password change, the choice of an organization, the start or end of a support session and entering or leaving an organization each issue a new token and end the old row, so a token never survives a change of privilege. support_tenant_id is set only on a super admin''s session during an audited read-only support session in that organization, until support_until. acting_tenant_id is set only on a super admin''s session after he entered that organization: until acting_until (60 minutes, never past the absolute expiry), until he leaves it or until the session ends, every organization request of the session acts inside it with every tenant role, on the application role and under its row-level security, and is audited as platform access. acting_exited_at records that the end of that access has been written to both audit logs, whichever way it ended, so it is audited exactly once; the sign-in upkeep audits the ends no request saw. A session holds a support organization or an acting organization, never both.';

ALTER TABLE platform_audit_entry DROP CONSTRAINT IF EXISTS platform_audit_entry_action_check;
ALTER TABLE platform_audit_entry ADD CONSTRAINT platform_audit_entry_action_check CHECK (action IN ('sign_in', 'sign_in_failed', 'sign_in_locked', 'organization_chosen', 'sign_out', 'session_expired', 'password_changed', 'password_change_failed', 'password_reset', 'account_created', 'account_updated', 'account_disabled', 'account_enabled', 'membership_added', 'membership_removed', 'organization_created', 'organization_renamed', 'organization_company_mode', 'organization_disabled', 'organization_enabled', 'support_session_started', 'support_session_ended', 'organization_entered', 'organization_exited', 'super_admin_created', 'super_admin_password_set'));

-- The function's result keeps its shape; only its body changes.
CREATE OR REPLACE FUNCTION resolve_session(p_token_hash bytea)
RETURNS TABLE (
  session_id            uuid,
  account_id            uuid,
  tenant_id             uuid,
  user_id               uuid,
  is_platform           boolean,
  support_tenant_id     uuid,
  acting_tenant_id      uuid,
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
    LEFT JOIN ontaix.password_credential pc ON pc.account_id = a.id
   WHERE s.token_hash = p_token_hash
     AND s.account_id = a.id
     AND s.ended_at IS NULL
     AND now() < s.idle_expires_at
     AND now() < s.absolute_expires_at
     AND a.disabled_at IS NULL
     AND (s.tenant_id IS NULL OR EXISTS (
           SELECT 1 FROM ontaix.account_membership m
           JOIN ontaix.tenant t ON t.id = m.tenant_id
          WHERE m.account_id = a.id AND m.tenant_id = s.tenant_id
            AND m.disabled_at IS NULL AND m.removed_at IS NULL AND t.disabled_at IS NULL))
  RETURNING s.id, a.id, s.tenant_id,
            (SELECT m.user_id FROM ontaix.account_membership m WHERE m.account_id = a.id AND m.tenant_id = s.tenant_id),
            a.is_platform,
            CASE WHEN s.support_until > now() THEN s.support_tenant_id END,
            CASE WHEN a.is_platform AND s.acting_until > now()
                      AND (SELECT x.disabled_at FROM ontaix.tenant x WHERE x.id = s.acting_tenant_id) IS NULL
                      AND EXISTS (SELECT 1 FROM ontaix.platform_role_assignment r WHERE r.account_id = a.id AND r.role = 'super_admin')
                 THEN s.acting_tenant_id END,
            coalesce(pc.must_change, false), s.csrf_token;
END;
$$;
COMMENT ON FUNCTION resolve_session(bytea) IS 'The only way the application role reads a session: given the SHA-256 of a presented cookie token, returns the live session''s account, the organization the session is inside and the account''s directory user there (both null for a member who has not chosen an organization yet, and for a platform account), platform flag, active support organization, the organization a super admin entered (null once its 60 minutes passed, when it is disabled, or when the account no longer holds super_admin), forced-change flag and CSRF token, and slides the 30-minute idle expiry (never past the absolute expiry). Returns no row for an unknown, ended or expired session, a disabled account, or a member session whose membership of its organization is disabled or removed or whose organization is disabled, so a removal or a disable takes effect at the next request. The caller then sets ontaix.tenant_id for the transaction; a session with must_change_password true may only read GET /auth/session, change its password and sign out.';

-- Both tables carry tenant_id and so get row-level security like every other such table; the
-- application role holds no privilege on either, and the platform role sees every row.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['account_membership', 'auth_session']
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
GRANT SELECT, INSERT, UPDATE, DELETE ON account_membership TO ontaix_platform;
REVOKE ALL ON account_membership FROM ontaix_app;
"""


def upgrade() -> None:
    """Add the enum value in its own committed transaction, then run the DDL on the raw psycopg
    cursor with no parameters, so `%` and backslashes stay."""
    with op.get_context().autocommit_block():
        op.execute(ENUM_DDL)
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0014 is one-way: PostgreSQL cannot drop an enum value")
