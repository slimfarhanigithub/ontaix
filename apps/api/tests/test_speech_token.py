"""POST /speech/token: the Speech SDK token, its gates, its budget, its audit entry, its
credential and the server-side exchange at a mocked STS endpoint."""

from __future__ import annotations

import base64
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from sqlalchemy import select

from app.clients import db_client
from app.clients.speech_token_client import (
    DEFAULT_STS_LIFETIME_SECONDS,
    EntraSpeechTokenClient,
    SpeechAccessToken,
    SpeechTokenUnavailable,
    _credential,
    issue_token_url,
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
ENTRA_TOKEN = "eyJhbGciOiJub25lIn0.eyJhdWQiOiJjb2duaXRpdmVzZXJ2aWNlcyJ9.ZW50cmE"
EXPIRES_ON = 1_900_000_000
STS_URL = "https://spch-ontaix-test-frc.cognitiveservices.azure.com/sts/v1.0/issueToken"


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


class EntraCredential:
    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes: str) -> AccessToken:
        self.scopes.append(scopes)
        return AccessToken(ENTRA_TOKEN, EXPIRES_ON)


class MockSts:
    """The Speech resource's `issueToken` endpoint: answers `status` with `body`, or raises."""

    def __init__(self, status: int = 200, body: str = "", error: Exception | None = None) -> None:
        self.status = status
        self.body = body
        self.error = error
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, text=self.body)


def sts_token(exp: int | None) -> str:
    claims: dict[str, object] = {"region": "francecentral"}
    if exp is not None:
        claims["exp"] = exp
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.c2lnbmF0dXJl"


def sts_client(sts: MockSts) -> EntraSpeechTokenClient:
    return EntraSpeechTokenClient(EntraCredential(), STS_URL, transport=sts.transport())


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
    async with db_client.get_platform_session_factory()() as s:
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
        "token": ACCESS_TOKEN,
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
    sts = MockSts(body=ACCESS_TOKEN)
    client = EntraSpeechTokenClient(
        FailingCredential(),  # type: ignore[arg-type]
        STS_URL,
        transport=sts.transport(),
    )

    with pytest.raises(SpeechTokenUnavailable) as raised:
        await client.access_token()

    assert str(raised.value) == "RuntimeError"
    assert sts.requests == []
    assert all(ACCESS_TOKEN not in r.getMessage() for r in caplog.records)


async def test_the_entra_token_is_exchanged_server_side_for_the_speech_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    exp = int(datetime.now(UTC).timestamp()) + 600
    issued = sts_token(exp)
    sts = MockSts(body=issued + "\n")
    credential = EntraCredential()
    client = EntraSpeechTokenClient(credential, STS_URL, transport=sts.transport())

    access = await client.access_token()

    assert access == SpeechAccessToken(token=issued, expires_on=exp)
    assert credential.scopes == [("https://cognitiveservices.azure.com/.default",)]
    (request,) = sts.requests
    assert (request.method, str(request.url)) == ("POST", STS_URL)
    assert request.headers["authorization"] == f"Bearer {ENTRA_TOKEN}"
    assert all(
        ENTRA_TOKEN not in r.getMessage() and issued not in r.getMessage() for r in caplog.records
    )


async def test_a_speech_token_without_a_readable_expiry_gets_the_default_lifetime() -> None:
    before = int(datetime.now(UTC).timestamp())

    for issued in (sts_token(None), sts_token(before - 60), "opaque-sts-token"):
        access = await sts_client(MockSts(body=issued)).access_token()

        assert access.token == issued
        assert before + DEFAULT_STS_LIFETIME_SECONDS <= access.expires_on
        assert access.expires_on <= before + DEFAULT_STS_LIFETIME_SECONDS + 5


@pytest.mark.parametrize(
    ("sts", "reason"),
    [
        (MockSts(status=401, body="Principal does not have access to API/Operation."), "HTTP 401"),
        (MockSts(status=500, body=ACCESS_TOKEN), "HTTP 500"),
        (MockSts(body="  "), "unusable token"),
        (MockSts(body="two words"), "unusable token"),
        (MockSts(error=httpx.ConnectError("refused")), "ConnectError"),
        (MockSts(error=httpx.ReadTimeout("slow")), "ReadTimeout"),
    ],
)
async def test_a_failed_exchange_is_unavailable_and_keeps_no_token(
    sts: MockSts, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SpeechTokenUnavailable) as raised:
        await sts_client(sts).access_token()

    assert str(raised.value) == reason
    assert all(
        ENTRA_TOKEN not in r.getMessage() and ACCESS_TOKEN not in r.getMessage()
        for r in caplog.records
    )


async def test_a_refused_exchange_answers_503_through_the_endpoint(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_resource_id", RESOURCE_ID)
    monkeypatch.setattr(settings, "speech_endpoint", ENDPOINT)
    set_speech_token_client(sts_client(MockSts(status=401)))
    try:
        response = await mint(client, tenant)
    finally:
        reset_speech_token_client()

    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"
    assert ENTRA_TOKEN not in response.text
    assert await speech_audit(tenant) == []


async def test_the_browser_receives_only_the_speech_token_from_the_exchange(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_resource_id", RESOURCE_ID)
    monkeypatch.setattr(settings, "speech_endpoint", ENDPOINT)
    exp = int(datetime.now(UTC).timestamp()) + 600
    issued = sts_token(exp)
    set_speech_token_client(sts_client(MockSts(body=issued)))
    try:
        response = await mint(client, tenant)
    finally:
        reset_speech_token_client()

    assert response.status_code == 200, response.text
    assert response.json()["token"] == issued
    assert response.json()["expiresAt"] == (
        datetime.fromtimestamp(exp, UTC).isoformat().replace("+00:00", "Z")
    )
    assert ENTRA_TOKEN not in response.text


async def test_the_issue_token_url_is_on_the_custom_subdomain() -> None:
    assert issue_token_url(ENDPOINT) == STS_URL
    assert issue_token_url(ENDPOINT.rstrip("/")) == STS_URL


async def test_the_dedicated_identity_is_used_whenever_its_client_id_is_set() -> None:
    client_id = "11111111-2222-3333-4444-555555555555"
    base = {"speech_resource_id": RESOURCE_ID, "speech_endpoint": ENDPOINT}

    for environment in ("dev", "production"):
        settings = settings_for(
            environment,
            speech_client_id=client_id,
            AZURE_FEDERATED_TOKEN_FILE="/var/run/secrets/azure/tokens/azure-identity-token",
            **base,
        )
        assert speech_configured(settings)
        assert isinstance(_credential(settings), ManagedIdentityCredential)
    assert not speech_configured(settings_for("dev", speech_client_id=client_id))


async def test_az_login_is_used_only_in_dev_and_never_under_workload_identity() -> None:
    base = {"speech_resource_id": RESOURCE_ID, "speech_endpoint": ENDPOINT}

    dev = settings_for("dev", **base)
    assert speech_configured(dev)
    assert isinstance(_credential(dev), AzureCliCredential)
    for settings in (
        settings_for("dev", AZURE_FEDERATED_TOKEN_FILE="/var/run/token", **base),
        settings_for("test", **base),
        settings_for("staging", **base),
        settings_for("production", **base),
    ):
        assert not speech_configured(settings)
        assert _credential(settings) is None


def settings_for(environment: str, **values: str) -> Settings:
    # The test process accepts the dev identity header; a production Settings must not.
    return Settings(  # type: ignore[call-arg]
        _env_file=None, ONTAIX_ENVIRONMENT=environment, dev_identity_header=False, **values
    )
