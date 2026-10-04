"""Appearance defaults of the design system: light theme, crimson accent, the categorical palette.

Brings a database of revision 0009 to the current `contracts/schema.sql`: the column defaults of
`tenant_settings.theme` (`light`) and `tenant_settings.accent` (`#d30c55`), and the colour of the
nine `domain_template` rows (the design system's categorical order: accent, link, good, human,
text-3, violet, teal, orange, olive). Only defaults and reference rows change: a tenant's saved
theme, accent and colour overrides are its own choices and stay as they are, and so do the
`tenant_domain` copies of the templates, since those are what a tenant's canvas already shows
(a tenant moves to the new palette through Appearance, Reset to defaults). Every statement is
idempotent, so on a database revision 0001 already created from the current contract this
revision changes nothing.

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

UPGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TABLE tenant_settings ALTER COLUMN theme SET DEFAULT 'light';
ALTER TABLE tenant_settings ALTER COLUMN accent SET DEFAULT '#d30c55';

UPDATE domain_template SET color = v.color
FROM (VALUES
  ('production', '#d30c55'),
  ('supply', '#2563eb'),
  ('sales', '#0e8a6a'),
  ('logistics', '#a07621'),
  ('quality', '#6f6a64'),
  ('maintenance', '#7c3aed'),
  ('finance', '#0e7490'),
  ('people', '#c2410c'),
  ('engineering', '#4d7c0f')
) AS v(key, color)
WHERE domain_template.key = v.key AND domain_template.color <> v.color;
"""

DOWNGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TABLE tenant_settings ALTER COLUMN theme SET DEFAULT 'dark';
ALTER TABLE tenant_settings ALTER COLUMN accent SET DEFAULT '#3fb8a9';

UPDATE domain_template SET color = v.color
FROM (VALUES
  ('production', '#3fb8a9'),
  ('supply', '#8b86cf'),
  ('sales', '#d9a15b'),
  ('logistics', '#d98b6b'),
  ('quality', '#cf7d98'),
  ('maintenance', '#7fb6d9'),
  ('finance', '#b9b36a'),
  ('people', '#8fbf7a'),
  ('engineering', '#c58ad0')
) AS v(key, color)
WHERE domain_template.key = v.key AND domain_template.color <> v.color;
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` stays literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(DOWNGRADE_DDL)
