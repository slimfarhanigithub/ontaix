"""Platform access: a super admin enters an organization and acts inside it with every role.

Brings a database of revision 0009 to the current `contracts/schema.sql`: the session end reason
`access_changed`; `auth_session.acting_tenant_id` with the constraint that a session holds a
support organization or an acting organization, never both; `resolve_session()` returning the
acting organization (null unless it is enabled), recreated because its result gains a column;
the `audit_entry` actor check that lets an entry of a user carry the super admin's account as
the platform access marker; and the platform log actions `organization_entered` and
`organization_exited`. Every statement is idempotent, so on a database already created from the
current contract this revision changes nothing. The DDL is the contract's text, so constraint
names and definitions match a database loaded from it.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-04
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ENUM_DDL = "ALTER TYPE ontaix.session_end_reason ADD VALUE IF NOT EXISTS 'access_changed'"

UPGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TABLE auth_session ADD COLUMN IF NOT EXISTS acting_tenant_id uuid REFERENCES tenant(id) ON DELETE CASCADE;
ALTER TABLE auth_session DROP CONSTRAINT IF EXISTS auth_session_one_access;
ALTER TABLE auth_session ADD CONSTRAINT auth_session_one_access CHECK (support_tenant_id IS NULL OR acting_tenant_id IS NULL);
COMMENT ON TABLE auth_session IS 'A server-side browser session. The cookie carries a 256-bit random token; only its SHA-256 is stored, so a database read never yields a usable cookie. A session is valid while ended_at is null, now() is before idle_expires_at (30 minutes, slid forward on use) and absolute_expires_at (12 hours after sign-in), the account is enabled and, for a member, the organization is enabled. Sign-in, a password change, the start or end of a support session and entering or leaving an organization each issue a new token and end the old row, so a token never survives a change of privilege. support_tenant_id is set only on a super admin''s session during an audited read-only support session in that organization, until support_until. acting_tenant_id is set only on a super admin''s session after he entered that organization: until he leaves it or the session ends, every organization request of the session acts inside it with every tenant role, on the application role and under its row-level security, and is audited as platform access. A session holds a support organization or an acting organization, never both.';

ALTER TABLE audit_entry DROP CONSTRAINT IF EXISTS audit_entry_platform_actor;
ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_platform_actor CHECK (CASE actor_kind WHEN 'platform' THEN actor_account_id IS NOT NULL WHEN 'user' THEN true ELSE actor_account_id IS NULL END);
COMMENT ON COLUMN audit_entry.actor_account_id IS 'The super admin''s platform account. Set always when actor_kind is platform, for the organization''s entries of kind platform (a user created, a password reset, a support session started or ended, the organization entered or left, the organization renamed, disabled or re-enabled, its company mode changed). Set on an entry of actor_kind user exactly when that user is the super admin acting inside the organization after entering it, which marks the entry as platform access; null for every other user entry, and always null for agent and system entries.';

ALTER TABLE platform_audit_entry DROP CONSTRAINT IF EXISTS platform_audit_entry_action_check;
ALTER TABLE platform_audit_entry ADD CONSTRAINT platform_audit_entry_action_check CHECK (action IN ('sign_in', 'sign_in_failed', 'sign_in_locked', 'sign_out', 'session_expired', 'password_changed', 'password_change_failed', 'password_reset', 'account_created', 'account_updated', 'account_disabled', 'account_enabled', 'organization_created', 'organization_renamed', 'organization_company_mode', 'organization_disabled', 'organization_enabled', 'support_session_started', 'support_session_ended', 'organization_entered', 'organization_exited', 'super_admin_created', 'super_admin_password_set'));

COMMENT ON TABLE app_user IS 'The native user directory of an organization. A user who signs in with a password has issuer ''local'' and the id of its account as subject, and is created with its account by a super admin; a user signing in through OIDC is provisioned on first sign-in into the tenant that owns the token issuer; the development seed''s users have issuer ''dev''. A super admin who enters the organization acts through a directory user with issuer ''platform'' and subject ''<account id>:<tenant id>'', created at the first entry, so that proposals, approvals and every other row he writes name a user of the organization; it belongs to no group and its roles come from the platform access alone. How a user authenticates never decides what the user may do.';
COMMENT ON TABLE platform_role_assignment IS 'Platform roles, held only by platform accounts (the composite foreign key refuses a member account). super_admin creates, renames, disables and enables organizations, sets their company mode, creates their accounts, resets passwords, opens audited read-only support sessions and enters organizations (auth_session.acting_tenant_id), where it holds every tenant role; it grants nothing inside an organization outside a support session or an entry. Written only by the local admin CLI.';

-- The function's result gains a column, which CREATE OR REPLACE cannot change.
DROP FUNCTION IF EXISTS resolve_session(bytea);
CREATE FUNCTION resolve_session(p_token_hash bytea)
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
            CASE WHEN a.is_platform AND (SELECT x.disabled_at FROM ontaix.tenant x WHERE x.id = s.acting_tenant_id) IS NULL
                 THEN s.acting_tenant_id END,
            coalesce(pc.must_change, false), s.csrf_token;
END;
$$;
COMMENT ON FUNCTION resolve_session(bytea) IS 'The only way the application role reads a session: given the SHA-256 of a presented cookie token, returns the live session''s account, organization, user, platform flag, active support organization, the organization a super admin entered (null unless it is enabled), forced-change flag and CSRF token, and slides the 30-minute idle expiry (never past the absolute expiry). Returns no row for an unknown, ended, expired or disabled session, account or organization. The caller then sets ontaix.tenant_id for the transaction; a session with must_change_password true may only read GET /auth/session, change its password and sign out.';
REVOKE ALL ON FUNCTION resolve_session(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_session(bytea) TO ontaix_app, ontaix_platform;
"""


def upgrade() -> None:
    """Add the enum value in its own committed transaction, then run the DDL on the raw psycopg
    cursor with no parameters, so `%` stays literal."""
    with op.get_context().autocommit_block():
        op.execute(ENUM_DDL)
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    raise NotImplementedError("revision 0010 is one-way")
