"""One theme: the design system's light theme, so a tenant has no theme setting.

Brings a database of revision 0011 to the current `contracts/schema.sql`: drops
`tenant_settings.theme` and the `theme_name` type. The appearance values a tenant still holds
from before the design system move with it: an accent on the old default (`#3fb8a9`) becomes the
crimson `#d30c55`, and a `tenant_domain` copy of a template still on that template's old colour
takes the template's categorical colour. Any other colour or accent stays, and so does the
`tenant_domain_revision` history; a tenant that picked the old default value itself moves with
the rest, since the stored value cannot tell the two apart. Every statement is idempotent, so on a database revision 0001
already created from the current contract this revision changes nothing.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-11
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UPGRADE_DDL = """
SET search_path TO ontaix, public;

UPDATE tenant_settings SET accent = '#d30c55' WHERE accent = '#3fb8a9';

UPDATE tenant_domain SET default_color = v.new_color
FROM (VALUES
  ('production', '#3fb8a9', '#d30c55'),
  ('supply', '#8b86cf', '#2563eb'),
  ('sales', '#d9a15b', '#0e8a6a'),
  ('logistics', '#d98b6b', '#a07621'),
  ('quality', '#cf7d98', '#6f6a64'),
  ('maintenance', '#7fb6d9', '#7c3aed'),
  ('finance', '#b9b36a', '#0e7490'),
  ('people', '#8fbf7a', '#c2410c'),
  ('engineering', '#c58ad0', '#4d7c0f')
) AS v(key, old_color, new_color)
WHERE tenant_domain.template_key = v.key AND tenant_domain.default_color = v.old_color;

ALTER TABLE tenant_settings DROP COLUMN IF EXISTS theme;
DROP TYPE IF EXISTS theme_name;
"""

DOWNGRADE_DDL = """
SET search_path TO ontaix, public;

DO $$ BEGIN
  CREATE TYPE theme_name AS ENUM ('dark', 'light');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS theme theme_name NOT NULL DEFAULT 'light';

UPDATE tenant_settings SET accent = '#3fb8a9' WHERE accent = '#d30c55';

UPDATE tenant_domain SET default_color = v.old_color
FROM (VALUES
  ('production', '#3fb8a9', '#d30c55'),
  ('supply', '#8b86cf', '#2563eb'),
  ('sales', '#d9a15b', '#0e8a6a'),
  ('logistics', '#d98b6b', '#a07621'),
  ('quality', '#cf7d98', '#6f6a64'),
  ('maintenance', '#7fb6d9', '#7c3aed'),
  ('finance', '#b9b36a', '#0e7490'),
  ('people', '#8fbf7a', '#c2410c'),
  ('engineering', '#c58ad0', '#4d7c0f')
) AS v(key, old_color, new_color)
WHERE tenant_domain.template_key = v.key AND tenant_domain.default_color = v.new_color;
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` stays literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(DOWNGRADE_DDL)
