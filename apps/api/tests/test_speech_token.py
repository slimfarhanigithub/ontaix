"""POST /speech/token: the Speech SDK token, its gates, its budget, its audit entry and its
credential."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from azure.identity import ManagedIdentityCredential
from sqlalchemy import select

from app.clients import db_client
from app.clients.speech_token_client import (
    EntraSpeechTokenClient,
    SpeechAccessToken,
    SpeechTokenUnavailable,
    _credential,
    reset_speech_token_client,
    set_speech_token_client,
    speech_configured,
)
from app.config import Settings, get_settings
from app.models.storage.audit_entry import AuditEntry
from tests.conftest import Persona, TenantFixture
from tests.test_teach import set_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

RESOURCE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-ontaix-test-frc"
    "/providers/Microsoft.CognitiveServices/accounts/spch-ontaix-test-frc"
)
ENDPOINT = "https://spch-ontaix-test-frc.cognitiveservices.azure.com/"
ACCESS_TOKEN = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJzcGVlY2gifQ.c2lnbmF0dXJl"
EXPIRES_ON = 1_900_000_000


class FakeSpeechTokenClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def access_token(self) -> SpeechAccessToken:
        self.calls += 1
        if self.fail:
            raise SpeechTokenUnavailable("CredentialUnavailableError")
        return SpeechAccessToken(token=ACCESS_TOKEN, expires_on=EXPIRES_ON)


class FailingCredential:
    def get_token(self, *scopes: str) -> object:
        raise RuntimeError(f"no identity for {ACCESS_TOKEN}")


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSpeechTokenClient]:
    """A configured Speech resource whose token client answers from memory."""
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_resource_id", RESOURCE_ID)
    monkeypatch.setattr(settings, "speech_endpoint", ENDPOINT)
    fake = FakeSpeechTokenClient()
    set_speech_token_client(fake)
    try:
        yield fake
    finally:
        reset_speech_token_client()


async def mint(
    client: httpx.AsyncClient, tenant: TenantFixture, persona: Persona | None = None
) -> httpx.Response:
    return await client.post(
        "/speech/token",
        json={"companyId": str(tenant.company_id)},
        headers=(persona or tenant.builder).headers,
    )


async def speech_audit(tenant: TenantFixture) -> list[AuditEntry]:
    async with db_client.get_session_factory()() as s:
        rows = await s.scalars(
            select(AuditEntry).where(
                AuditEntry.tenant_id == tenant.tenant_id, AuditEntry.kind == "speech"
            )
        )
        return list(rows)


async def test_a_teacher_gets_an_sdk_token_that_is_not_cached_and_is_audited(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    speech: FakeSpeechTokenClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    response = await mint(client, tenant)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "token": f"aad#{RESOURCE_ID}#{ACCESS_TOKEN}",
        "region": "francecentral",
        "expiresAt": datetime.fromtimestamp(EXPIRES_ON, UTC).isoformat().replace("+00:00", "Z"),
        "language": "en-GB",
    }
    (entry,) = await speech_audit(tenant)
    assert (entry.what, entry.ok, entry.proposal_id) == (
        "Speech recognition token issued",
        True,
        None,
    )
    assert entry.company_ids == [tenant.company_id]
    assert entry.actor_user_id == tenant.builder.user_id
    assert all(ACCESS_TOKEN not in r.getMessage() for r in caplog.records)


async def test_the_company_owner_may_mint_and_the_language_follows_configuration(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    speech: FakeSpeechTokenClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "speech_language", "en-US")

    response = await mint(client, tenant, tenant.owner)

    assert response.status_code == 200, response.text
    assert response.json()["language"] == "en-US"


async def test_callers_who_may_not_teach_are_refused_and_nothing_is_minted(
    client: httpx.AsyncClient, tenant: TenantFixture, speech: FakeSpeechTokenClient
) -> None:
    governor = await mint(client, tenant, tenant.governor)
    outsider = await mint(client, tenant, tenant.outsider)
    unknown = await client.post(
        "/speech/token", json={"companyId": str(uuid.uuid4())}, headers=tenant.builder.headers
    )

    assert governor.status_code == 403
    assert outsider.status_code == 404
    assert unknown.status_code == 404
    assert speech.calls == 0
    assert await speech_audit(tenant) == []


async def test_voice_off_refuses_with_channel_disabled(
    client: httpx.AsyncClient, tenant: TenantFixture, speech: FakeSpeechTokenClient
) -> None:
    await set_settings(tenant, voice=False)

    response = await mint(client, tenant)

    assert response.status_code == 409
    assert response.json()["code"] == "channel_disabled"
    assert speech.calls == 0


async def test_the_hourly_speech_budget_refuses_with_retry_after(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    speech: FakeSpeechTokenClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "speech_tokens_per_hour", 2)

    statuses = [(await mint(client, tenant)).status_code for _ in range(3)]
    refused = await mint(client, tenant)

    assert statuses == [200, 200, 429]
    assert refused.json()["code"] == "rate_limited"
    assert int(refused.headers["retry-after"]) >= 1
    assert speech.calls == 2
    assert len(await speech_audit(tenant)) == 2


async def test_no_speech_resource_answers_503_without_charging(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "speech_tokens_per_hour", 1)
    reset_speech_token_client()

    first = await mint(client, tenant)
    second = await mint(client, tenant)

    assert (first.status_code, second.status_code) == (503, 503)
    assert first.json()["code"] == "unavailable"
    assert await speech_audit(tenant) == []


async def test_a_token_that_cannot_be_minted_answers_503_and_is_not_audited(
    client: httpx.AsyncClient, tenant: TenantFixture, speech: FakeSpeechTokenClient
) -> None:
    speech.fail = True

    response = await mint(client, tenant)

    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"
    assert ACCESS_TOKEN not in response.text
    assert await speech_audit(tenant) == []


async def test_a_credential_failure_keeps_only_its_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = EntraSpeechTokenClient(FailingCredential())  # type: ignore[arg-type]

    with pytest.raises(SpeechTokenUnavailable) as raised:
        await client.access_token()

    assert str(raised.value) == "RuntimeError"
    assert all(ACCESS_TOKEN not in r.getMessage() for r in caplog.records)


async def test_only_the_dedicated_identity_mints_in_every_environment() -> None:
    client_id = "11111111-2222-3333-4444-555555555555"
    base = {"speech_resource_id": RESOURCE_ID, "speech_endpoint": ENDPOINT}

    for environment in ("dev", "production"):
        assert speech_configured(settings_for(environment, speech_client_id=client_id, **base))
        assert not speech_configured(settings_for(environment, **base))
    assert not speech_configured(settings_for("dev", speech_client_id=client_id))
    assert isinstance(_credential(client_id), ManagedIdentityCredential)


def settings_for(environment: str, **values: str) -> Settings:
    return Settings(_env_file=None, ONTAIX_ENVIRONMENT=environment, **values)  # type: ignore[call-arg]
