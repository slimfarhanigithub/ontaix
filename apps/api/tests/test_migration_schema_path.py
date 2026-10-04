"""Revision 0001 finds the schema contract wherever the migration file sits.

In a checkout the contract is `contracts/schema.sql` above the package; in the API image the
module sits at /app/app/migrations/versions with no repository above it and ONTAIX_SCHEMA_SQL
names the copy the image carries. Importing the module never touches the filesystem.
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
from pathlib import Path

import pytest

MODULE_NAME = "app.migrations.versions.0001_initial_schema"


def _module():
    return importlib.import_module(MODULE_NAME)


def test_import_from_a_shallow_path_does_not_resolve_the_contract(tmp_path: Path) -> None:
    source = Path(_module().__file__)
    shallow = tmp_path / "app" / "app" / "migrations" / "versions"
    shallow.mkdir(parents=True)
    copied = shutil.copy(source, shallow / source.name)

    spec = importlib.util.spec_from_file_location("shallow_0001", copied)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0001"


def test_configured_path_wins(tmp_path: Path) -> None:
    contract = tmp_path / "schema.sql"
    contract.write_text("SELECT 1;\n", encoding="utf-8")
    module = _module()

    found = module.schema_sql_path(
        Path("/app/app/migrations/versions/0001_initial_schema.py"),
        {module.SCHEMA_SQL_ENV: str(contract)},
    )

    assert found == contract


def test_configured_path_must_exist(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(FileNotFoundError, match=module.SCHEMA_SQL_ENV):
        module.schema_sql_path(Path(module.__file__), {module.SCHEMA_SQL_ENV: str(tmp_path / "x")})


def test_repository_contract_is_found_above_the_module() -> None:
    module = _module()

    found = module.schema_sql_path(Path(module.__file__), {})

    assert found.name == "schema.sql"
    assert found.parent.name == "contracts"
    assert found.is_file()


def test_shallow_module_without_a_repository_fails_clearly(tmp_path: Path) -> None:
    module = _module()
    shallow = tmp_path / "app" / "app" / "migrations" / "versions" / "0001_initial_schema.py"

    with pytest.raises(FileNotFoundError, match=module.SCHEMA_SQL_ENV):
        module.schema_sql_path(shallow, {})
