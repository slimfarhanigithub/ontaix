"""The `live` and `deep` model profiles: settings fallback, one client per profile, the model
recorded per profile, and which teach path uses which profile."""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest

import app.clients.anthropic_foundry_llm_client as claude
import app.clients.llm_client as llm_client
from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS
from app.clients.anthropic_foundry_llm_client import AnthropicFoundryLlmClient
from app.clients.llm_client import LlmConfigurationError, get_llm_client, set_llm_client
from app.config import LlmProfileSettings, ModelPrice, Settings, get_settings
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient, recorded
from tests.test_teach_extraction import FIRST, add_company, configure, rows, teach
from tests.test_teach_speech import TRANSCRIPT, speak

ENDPOINT = "https://ais-ontaix-dev-frc-abcde.cognitiveservices.azure.com/"
SONNET = ModelPrice(inputEurPerMTok=Decimal("3.44"), outputEurPerMTok=Decimal("17.2"))
FABLE = ModelPrice(inputEurPerMTok=Decimal("8.6"), outputEurPerMTok=Decimal("43.0"))


def claude_settings(**values: object) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="anthropic_foundry",
        foundry_endpoint=ENDPOINT,
        foundry_deployment="claude-sonnet-5",
        foundry_reasoning_effort="none",
        llm_price_table={"claude-sonnet-5": SONNET, "claude-fable-5-1": FABLE},
        **values,
    )


@pytest.fixture
def keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_token() -> str:
        return "eyJfake.PROFILE.sig"

    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
    monkeypatch.setattr(llm_client, "_cached", {})


def test_an_unset_deep_profile_takes_every_live_value() -> None:
    settings = Settings(
        _env_file=None,
        foundry_deployment="claude-sonnet-5",
        foundry_reasoning_effort="none",
        llm_reasoning_allowance_tokens=128,
    )

    assert settings.llm_profile("deep") == settings.llm_profile("live")
    assert settings.llm_profile("live") == LlmProfileSettings("claude-sonnet-5", "none", 128)


def test_each_deep_setting_overrides_its_live_value_alone(monkeypatch) -> None:
    monkeypatch.setenv("ONTAIX_FOUNDRY_DEPLOYMENT", "claude-sonnet-5")
    monkeypatch.setenv("ONTAIX_LLM_REASONING_ALLOWANCE_TOKENS", "256")
    monkeypatch.setenv("ONTAIX_FOUNDRY_DEEP_DEPLOYMENT", "claude-fable-5-1")
    monkeypatch.setenv("ONTAIX_FOUNDRY_DEEP_REASONING_EFFORT", "low")
    monkeypatch.setenv("ONTAIX_LLM_DEEP_REASONING_ALLOWANCE_TOKENS", "")

    settings = Settings(_env_file=None)

    assert settings.llm_profile("deep") == LlmProfileSettings("claude-fable-5-1", "low", 256)
    assert settings.llm_profile("live") == LlmProfileSettings("claude-sonnet-5", "none", 256)
    assert (
        Settings(_env_file=None, llm_deep_reasoning_allowance_tokens=0)
        .llm_profile("deep")
        .reasoning_allowance_tokens
        == 0
    )


@pytest.mark.parametrize(
    "values",
    [
        {"foundry_deep_deployment": "bad name"},
        {"foundry_deep_reasoning_effort": "extreme"},
        {"llm_deep_reasoning_allowance_tokens": 16_385},
        {"llm_deep_reasoning_allowance_tokens": -1},
    ],
)
def test_the_deep_settings_are_validated_as_the_live_ones(values: dict) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_each_profile_has_its_own_cached_client_recording_its_deployment(keyless) -> None:
    settings = claude_settings(
        foundry_deep_deployment="claude-fable-5-1", foundry_deep_reasoning_effort="low"
    )

    llm_client.check_llm_configuration(settings)
    live = llm_client._configured(settings, "live")
    deep = llm_client._configured(settings, "deep")

    assert isinstance(live, AnthropicFoundryLlmClient)
    assert isinstance(deep, AnthropicFoundryLlmClient)
    assert live is not deep
    assert (live.model, live._price) == ("claude-sonnet-5", SONNET)
    assert (deep.model, deep._price) == ("claude-fable-5-1", FABLE)
    assert live.capabilities["thinking"] == {"type": "disabled"}
    assert deep.capabilities["output_config"] == {"effort": "low"}
    assert llm_client._configured(settings, "live") is live
    assert llm_client._configured(settings, "deep") is deep


def test_the_foundry_providers_price_the_deployment_not_the_model_setting() -> None:
    settings = claude_settings(llm_model="gpt-6-sol")

    assert llm_client._priced_model(settings, "live") == "claude-sonnet-5"
    azure = Settings(
        _env_file=None,
        foundry_deployment="gpt-6-sol-frc",
        llm_model="gpt-6-sol",
    )
    assert llm_client._priced_model(azure, "deep") == "gpt-6-sol-frc"


def test_an_unpriced_deep_deployment_stops_start_up() -> None:
    settings = claude_settings(foundry_deep_deployment="claude-opus-5-5")

    with pytest.raises(LlmConfigurationError, match="deep"):
        llm_client.check_llm_configuration(settings)


def test_set_llm_client_replaces_one_profile_or_both() -> None:
    live, deep = FakeLlmClient(), FakeLlmClient()

    set_llm_client(live)
    assert get_llm_client("live") is live and get_llm_client("deep") is live
    set_llm_client(deep, "deep")
    assert get_llm_client() is live and get_llm_client("deep") is deep


def profile_fakes() -> tuple[FakeLlmClient, FakeLlmClient]:
    live, deep = FakeLlmClient(), FakeLlmClient()
    live.model, deep.model = "claude-sonnet-5", "claude-fable-5-1"
    set_llm_client(live, "live")
    set_llm_client(deep, "deep")
    return live, deep


async def recorded_models(tenant: TenantFixture) -> list[str]:
    found = await rows("SELECT model FROM ontaix.llm_call WHERE tenant_id = :t", t=tenant.tenant_id)
    return [r["model"] for r in found]


@pytest.mark.asyncio(loop_scope="session")
async def test_typed_text_runs_on_the_live_profile(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    live, deep = profile_fakes()
    live.answer(recorded("insight_sells_services"))

    await teach(client, tenant, company_id, FIRST, uuid.uuid4())

    assert (len(live.requests), len(deep.requests)) == (1, 0)
    assert await recorded_models(tenant) == ["claude-sonnet-5"]


@pytest.mark.asyncio(loop_scope="session")
async def test_speech_runs_on_the_live_profile(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    live, deep = profile_fakes()
    live.answer(recorded("speech_insight_transcript"))

    await speak(client, tenant, company_id, TRANSCRIPT)

    assert (len(live.requests), len(deep.requests)) == (1, 0)
    assert await recorded_models(tenant) == ["claude-sonnet-5"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_document_sentence_runs_on_the_deep_profile_with_its_allowance(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch
) -> None:
    await configure(tenant)
    live, deep = profile_fakes()
    deep.answer(recorded("insight_sells_services"))
    upload = await client.post(
        "/import/sentences",
        files={"file": ("brief.txt", f"{FIRST}.".encode(), "text/plain")},
        headers=tenant.builder.headers,
    )
    assert upload.status_code == 200, upload.text
    import_ref = {"importId": upload.json()["importId"], "sentenceIndex": 0}
    monkeypatch.setenv("ONTAIX_LLM_REASONING_ALLOWANCE_TOKENS", "0")
    monkeypatch.setenv("ONTAIX_LLM_DEEP_REASONING_ALLOWANCE_TOKENS", "4096")
    get_settings.cache_clear()
    try:
        await teach(client, tenant, tenant.company_id, import_ref=import_ref)
    finally:
        get_settings.cache_clear()

    assert (len(live.requests), len(deep.requests)) == (0, 1)
    assert deep.requests[0].max_output_tokens == MAX_OUTPUT_TOKENS + 4096
    assert await recorded_models(tenant) == ["claude-fable-5-1"]
