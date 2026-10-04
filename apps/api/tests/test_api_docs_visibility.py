"""The interactive documentation and the OpenAPI document are served outside production only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.main import create_app

DOCUMENTATION_PATHS = {"/docs", "/redoc", "/openapi.json"}
ENVIRONMENT_VARIABLES = ("ONTAIX_ENVIRONMENT", "ONTAIX_ENV", "ONTAIX_DEV_IDENTITY_HEADER")


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[pytest.MonkeyPatch]:
    """No environment variable and no `.env` file; process settings are rebuilt around the test."""
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _served_paths(application: object) -> set[str]:
    return {getattr(route, "path", "") for route in getattr(application, "routes", [])}


def test_production_serves_no_documentation(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("ONTAIX_ENVIRONMENT", "production")
    get_settings.cache_clear()

    application = create_app()

    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None
    assert not DOCUMENTATION_PATHS & _served_paths(application)


def test_missing_environment_is_production_and_serves_no_documentation(
    environment: pytest.MonkeyPatch,
) -> None:
    application = create_app()

    assert not DOCUMENTATION_PATHS & _served_paths(application)


@pytest.mark.parametrize("name", ["dev", "test", "staging"])
def test_other_environments_serve_the_documentation(
    environment: pytest.MonkeyPatch, name: str
) -> None:
    environment.setenv("ONTAIX_ENVIRONMENT", name)
    get_settings.cache_clear()

    application = create_app()

    assert DOCUMENTATION_PATHS <= _served_paths(application)
