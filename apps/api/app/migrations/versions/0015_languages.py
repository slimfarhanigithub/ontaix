"""Languages: the account's portal language and the company's model language.

Brings a database of revision 0014 to the current `contracts/schema.sql`: `account.language`
(`en`, `fr` or `de`, null when the person follows the browser) and `company.language` (`en`,
`fr` or `de`, `en` by default). Every statement is idempotent, so on a database revision 0001
already created from the current contract this revision changes nothing. The DDL is the
contract's text, so constraint names and definitions match a database loaded from it. The
downgrade drops the two columns.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-29
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TABLE account ADD COLUMN IF NOT EXISTS language text CHECK (language IN ('en', 'fr', 'de'));
COMMENT ON COLUMN account.language IS 'The portal language the person chose (en, fr or de): every label of the Studio and the admin portal, dates and numbers, never ontology content. Null follows the browser''s language when it is one of the three, else English. Set by the person alone (PUT /auth/session/language).';

ALTER TABLE company ADD COLUMN IF NOT EXISTS language text NOT NULL DEFAULT 'en' CHECK (language IN ('en', 'fr', 'de'));
COMMENT ON COLUMN company.language IS 'The model language of the company (en, fr or de): the speech recognition locale and phrase list, the language the teach, document extraction and expansion models write new labels, specs and relation verbs in, the instant grammar drafts, and the language tags and fixed text of an export. Chosen at creation and changed by an Administrator (PATCH /companies/{id}/language), immediately and audited; a company setting, not a proposal. Changing it never translates existing concepts.';
"""

DOWNGRADE_DDL = """
SET search_path TO ontaix, public;

ALTER TABLE company DROP COLUMN IF EXISTS language;
ALTER TABLE account DROP COLUMN IF EXISTS language;
"""


def upgrade() -> None:
    """Run the DDL on the raw psycopg cursor with no parameters: `%` stays literal."""
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(UPGRADE_DDL)


def downgrade() -> None:
    with op.get_bind().connection.dbapi_connection.cursor() as cursor:
        cursor.execute(DOWNGRADE_DDL)
