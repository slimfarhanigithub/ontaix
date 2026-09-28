"""The dev identity header is accepted only when the environment is exactly `dev`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from tests.conftest import TenantFixture

ENVIRONMENT_VARIABLES = ("ONTAIX_ENVIRONMENT", "ONTAIX_ENV")


@pytest.fixture
def no_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[pytest.MonkeyPatch]:
    """No environment variable and no `.env` file; process settings are rebuilt around the test."""
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_missing_environment_is_not_dev(no_environment: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.is_dev is False


def test_misspelled_environment_variable_is_not_dev(no_environment: pytest.MonkeyPatch) -> None:
    no_environment.setenv("ONTAIX_ENVIROMENT", "dev")

    assert Settings(_env_file=None).is_dev is False


@pytest.mark.parametrize("value", ["Dev", "DEV", "develop", "dev ", "prod"])
def test_unknown_environment_value_stops_startup(
    no_environment: pytest.MonkeyPatch, value: str
) -> None:
    no_environment.setenv("ONTAIX_ENVIRONMENT", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["production", "staging", "test"])
def test_known_non_dev_environment_is_not_dev(
    no_environment: pytest.MonkeyPatch, value: str
) -> None:
    no_environment.setenv("ONTAIX_ENVIRONMENT", value)

    assert Settings(_env_file=None).is_dev is False


def test_only_exact_dev_enables_the_header(no_environment: pytest.MonkeyPatch) -> None:
    no_environment.setenv("ONTAIX_ENV", "dev")

    assert Settings(_env_file=None).is_dev is True


@pytest.mark.parametrize("value", [None, "production"])
async def test_dev_header_is_refused_outside_dev(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    no_environment: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is not None:
        no_environment.setenv("ONTAIX_ENVIRONMENT", value)
    get_settings.cache_clear()

    response = await client.get("/scene", headers=tenant.governor.headers)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "unauthorized"
