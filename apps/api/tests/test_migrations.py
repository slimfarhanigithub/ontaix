"""Revision 0002 brings a database of the earlier schema contract to the current one.

Database A is created by revision 0001 from the earlier contract (tests/fixtures/schema_0001.sql)
and then upgraded to head; database B is `contracts/schema.sql` loaded directly. Their catalogs
must be identical: columns (not their ordinal positions, which a dropped column shifts),
constraints, indexes, enum labels, triggers, functions and comments.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.migrations.runner import API_ROOT

OLD_SCHEMA = Path(__file__).parent / "fixtures" / "schema_0001.sql"
CONTRACT = API_ROOT.parents[1] / "contracts" / "schema.sql"

CATALOG_QUERIES: dict[str, str] = {
    "columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns WHERE table_schema = 'ontaix'
        ORDER BY table_name, column_name""",
    "constraints": """
        SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'ontaix' ORDER BY 1, 2""",
    "indexes": """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = 'ontaix' ORDER BY 1, 2""",
    "enums": """
        SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
        FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'ontaix' GROUP BY t.typname ORDER BY 1""",
    "triggers": """
        SELECT t.tgrelid::regclass::text, t.tgname, pg_get_triggerdef(t.oid)
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ontaix' AND NOT t.tgisinternal ORDER BY 1, 2""",
    "functions": """
        SELECT p.proname, pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'ontaix' ORDER BY 1""",
    "table_comments": """
        SELECT c.relname, obj_description(c.oid, 'pg_class')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ontaix' AND c.relkind = 'r' ORDER BY 1""",
    "column_comments": """
        SELECT c.relname, a.attname, col_description(c.oid, a.attnum)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE n.nspname = 'ontaix' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped ORDER BY 1, 2""",
}


@pytest.fixture
def scratch_databases(database_url: str) -> Iterator[tuple[str, str]]:
    names = [f"ontaix_mig_{uuid.uuid4().hex[:8]}" for _ in range(2)]
    with psycopg.connect(database_url, autocommit=True) as admin:
        for name in names:
            admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _url_for(database_url, names[0]), _url_for(database_url, names[1])
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            for name in names:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_upgrade_from_0001_matches_the_schema_contract(
    scratch_databases: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated_url, contract_url = scratch_databases
    monkeypatch.setenv("ONTAIX_SCHEMA_SQL", str(OLD_SCHEMA))
    _upgrade(migrated_url, "0001")
    with psycopg.connect(migrated_url) as conn:
        demo_story = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = 'ontaix'"
            " AND table_name = 'tenant_settings' AND column_name = 'demo_story'"
        ).fetchone()
    assert demo_story is not None, "the fixture must build the earlier schema"
    monkeypatch.delenv("ONTAIX_SCHEMA_SQL")
    _upgrade(migrated_url, "head")

    with psycopg.connect(contract_url, autocommit=True) as conn:
        conn.execute(CONTRACT.read_text(encoding="utf-8"))

    with psycopg.connect(migrated_url) as a, psycopg.connect(contract_url) as b:
        for name, query in CATALOG_QUERIES.items():
            got, want = a.execute(query).fetchall(), b.execute(query).fetchall()
            assert got == want, f"{name} differ: {sorted(set(got) ^ set(want))[:10]}"


def test_upgrade_is_a_no_op_on_a_database_created_from_the_contract(
    scratch_databases: tuple[str, str],
) -> None:
    migrated_url, contract_url = scratch_databases
    _upgrade(migrated_url, "head")
    with psycopg.connect(contract_url, autocommit=True) as conn:
        conn.execute(CONTRACT.read_text(encoding="utf-8"))
    with psycopg.connect(migrated_url) as a, psycopg.connect(contract_url) as b:
        for name, query in CATALOG_QUERIES.items():
            assert a.execute(query).fetchall() == b.execute(query).fetchall(), name


def _upgrade(url: str, target: str) -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "app" / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, target)


def _url_for(url: str, database: str) -> str:
    """The same server URL with another database name, keeping any query string."""
    head, _, query = url.partition("?")
    base = head.rsplit("/", 1)[0]
    return f"{base}/{database}" + (f"?{query}" if query else "")
