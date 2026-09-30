"""The dev identity header is accepted only in dev or test with ONTAIX_DEV_IDENTITY_HEADER on.

The flag defaults to off, so a deployed environment named `dev` accepts no header, and the
process refuses to start with the flag on in any other environment.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from tests.conftest import TenantFixture

ENVIRONMENT_VARIABLES = ("ONTAIX_ENVIRONMENT", "ONTAIX_ENV", "ONTAIX_DEV_IDENTITY_HEADER")


@pytest.fixture
def no_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[pytest.MonkeyPatch]:
    """No environment variable and no `.env` file; process settings are rebuilt around the test."""
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_missing_environment_accepts_no_header(no_environment: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.dev_identity_header is False
    assert settings.accepts_dev_identity_header is False


def test_misspelled_environment_variable_accepts_no_header(
    no_environment: pytest.MonkeyPatch,
) -> None:
    no_environment.setenv("ONTAIX_ENVIROMENT", "dev")

    assert Settings(_env_file=None).accepts_dev_identity_header is False


@pytest.mark.parametrize("value", ["Dev", "DEV", "develop", "dev ", "prod"])
def test_unknown_environment_value_stops_startup(
    no_environment: pytest.MonkeyPatch, value: str
) -> None:
    no_environment.setenv("ONTAIX_ENVIRONMENT", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["dev", "test"])
def test_dev_or_test_without_the_flag_accepts_no_header(
    no_environment: pytest.MonkeyPatch, value: str
) -> None:
    no_environment.setenv("ONTAIX_ENVIRONMENT", value)

    assert Settings(_env_file=None).accepts_dev_identity_header is False


@pytest.mark.parametrize("value", ["dev", "test"])
def test_dev_or_test_with_the_flag_accepts_the_header(
    no_environment: pytest.MonkeyPatch, value: str
) -> None:
    no_environment.setenv("ONTAIX_ENV", value)
    no_environment.setenv("ONTAIX_DEV_IDENTITY_HEADER", "true")

    assert Settings(_env_file=None).accepts_dev_identity_header is True


@pytest.mark.parametrize("value", [None, "production", "staging"])
def test_the_flag_outside_dev_or_test_stops_startup(
    no_environment: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is not None:
        no_environment.setenv("ONTAIX_ENVIRONMENT", value)
    no_environment.setenv("ONTAIX_DEV_IDENTITY_HEADER", "true")

    with pytest.raises(ValidationError, match="ONTAIX_DEV_IDENTITY_HEADER"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("environment", "flag"), [(None, None), ("production", None), ("dev", None)]
)
async def test_dev_header_is_refused_without_dev_or_test_and_the_flag(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    no_environment: pytest.MonkeyPatch,
    environment: str | None,
    flag: str | None,
) -> None:
    if environment is not None:
        no_environment.setenv("ONTAIX_ENVIRONMENT", environment)
    if flag is not None:
        no_environment.setenv("ONTAIX_DEV_IDENTITY_HEADER", flag)
    get_settings.cache_clear()

    response = await client.get("/scene", headers=tenant.governor.headers)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "unauthorized"


async def test_dev_header_is_accepted_in_test_with_the_flag(
    client: httpx.AsyncClient, tenant: TenantFixture, no_environment: pytest.MonkeyPatch
) -> None:
    no_environment.setenv("ONTAIX_ENVIRONMENT", "test")
    no_environment.setenv("ONTAIX_DEV_IDENTITY_HEADER", "true")
    get_settings.cache_clear()

    response = await client.get("/scene", headers=tenant.governor.headers)

    assert response.status_code == 200, response.text
