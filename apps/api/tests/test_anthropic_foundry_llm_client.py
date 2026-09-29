"""Claude on Azure AI Foundry over an in-memory HTTP transport and a fake Entra ID token."""

from __future__ import annotations

import json
from decimal import Decimal

import anthropic
import httpx2
import jsonschema
import pytest

import app.clients.anthropic_foundry_llm_client as claude
import app.clients.llm_client as llm_client
from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.clients.anthropic_foundry_llm_client import (
    AnthropicFoundryLlmClient,
    foundry_messages_url,
    thinking_options,
)
from app.clients.llm_client import LlmProviderError, LlmRequest
from app.config import ModelPrice, Settings
from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from tests.llm_fakes import recorded

# A made-up value, not a credential.
TOKEN = "eyJfake.CLAUDE.sig"
PRICE = ModelPrice(inputEurPerMTok=Decimal("3"), outputEurPerMTok=Decimal("15"))
BASE_URL = "https://ais-ontaix-dev-sdc-eval-abcde.services.ai.azure.com/anthropic/"


def message(text: str, stop: str = "end_turn") -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "text", "text": text},
        ],
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 700,
            "output_tokens": 300,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 100,
        },
    }


def install(monkeypatch: pytest.MonkeyPatch, body: dict, status: int = 200) -> list:
    seen: list[httpx2.Request] = []
    pools: list[dict] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx2.Response(404, json={"error": "not found"})
        return httpx2.Response(status, json=body)

    def pool(**options: object) -> httpx2.AsyncClient:
        pools.append(options)
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **options)

    tokens: list[str] = []

    async def fake_token() -> str:
        tokens.append(TOKEN)
        return TOKEN

    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", pool)
    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
    install.pools, install.tokens = pools, tokens  # type: ignore[attr-defined]
    return seen


def request() -> LlmRequest:
    return LlmRequest(SYSTEM_PROMPT, '{"sentence": "x"}', OUTPUT_SCHEMA, MAX_OUTPUT_TOKENS, 5.0)


def test_efforts_map_to_thinking_settings() -> None:
    assert thinking_options(None) == {}
    assert thinking_options("none") == {"thinking": {"type": "disabled"}}
    assert thinking_options("minimal")["output_config"] == {"effort": "low"}
    assert thinking_options("high") == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
    }


def test_the_messages_url_comes_from_any_endpoint_of_the_resource() -> None:
    assert (
        foundry_messages_url("https://ais-ontaix-dev-sdc-eval-abcde.cognitiveservices.azure.com/")
        == BASE_URL
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_a_structured_answer_with_thinking_counts_every_token(monkeypatch) -> None:
    seen = install(monkeypatch, message(recorded("insight_sells_services")))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", PRICE, "medium")

    answer = await client.complete(request())

    assert json.loads(answer.text) == json.loads(recorded("insight_sells_services"))
    assert (answer.input_tokens, answer.output_tokens) == (800, 300)
    # The 100 cache-read tokens cost a tenth of the input price.
    assert answer.cost_eur == pytest.approx((700 * 3 + 100 * 3 * 0.1 + 300 * 15) / 1e6)
    (sent,) = seen
    assert str(sent.url).startswith(BASE_URL)
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(sent.content)
    assert body["model"] == "claude-sonnet-5-5"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio(loop_scope="session")
async def test_a_refusal_and_a_failed_status_are_provider_errors(monkeypatch) -> None:
    seen = install(monkeypatch, message("", stop="refusal"))
    with pytest.raises(LlmProviderError) as refused:
        await AnthropicFoundryLlmClient(BASE_URL, "claude-opus-5-5", PRICE, "low").complete(
            request()
        )
    assert str(refused.value) == "refusal" and len(seen) == 1

    seen = install(monkeypatch, {"type": "error", "error": {"type": "overloaded"}}, status=529)
    with pytest.raises(LlmProviderError) as failed:
        await AnthropicFoundryLlmClient(BASE_URL, "claude-opus-5-5", PRICE, "low").complete(
            request()
        )
    assert str(failed.value) == "status" and len(seen) == 1


def test_the_factory_builds_claude_on_foundry_from_the_foundry_settings(monkeypatch) -> None:
    async def fake_token() -> str:
        return TOKEN

    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
    monkeypatch.setattr(llm_client, "_cached", {})
    settings = Settings(
        _env_file=None,
        llm_provider="anthropic_foundry",
        foundry_endpoint="https://ais-ontaix-dev-sdc-abcde.cognitiveservices.azure.com/",
        foundry_deployment="claude-fable-5-1",
        foundry_reasoning_effort="low",
        llm_model="claude-fable-5-1",
        llm_price_table={"claude-fable-5-1": PRICE},
    )

    llm_client.check_llm_configuration(settings)
    built = llm_client._configured(settings, "live")

    assert isinstance(built, AnthropicFoundryLlmClient)
    assert built.model == "claude-fable-5-1"
    assert built.capabilities["output_config"] == {"effort": "low"}
    assert str(built._client.base_url) == (
        "https://ais-ontaix-dev-sdc-abcde.services.ai.azure.com/anthropic/"
    )


def test_claude_on_foundry_without_an_endpoint_is_not_configured() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="anthropic_foundry",
        foundry_endpoint=None,
        llm_model="claude-fable-5-1",
    )

    llm_client.check_llm_configuration(settings)
    assert llm_client._configured(settings, "live") is None


def usage_message(text: str, written: int, read: int) -> dict:
    body = message(text)
    body["usage"] = {
        "input_tokens": 50,
        "output_tokens": 10,
        "cache_creation_input_tokens": written,
        "cache_read_input_tokens": read,
    }
    return body


@pytest.mark.asyncio(loop_scope="session")
async def test_the_system_prompt_is_one_cached_block_byte_identical_on_every_call(
    monkeypatch,
) -> None:
    seen = install(monkeypatch, message(recorded("insight_sells_services")))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")

    await client.complete(request())
    await client.complete(
        LlmRequest(SYSTEM_PROMPT, '{"sentence": "y"}', OUTPUT_SCHEMA, MAX_OUTPUT_TOKENS, 5.0)
    )

    first, second = (json.loads(sent.content) for sent in seen)
    assert first["system"] == [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ]
    assert second["system"] == first["system"]
    # The per-call data follows the breakpoint and is never cached.
    assert second["messages"] == [{"role": "user", "content": '{"sentence": "y"}'}]


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_writes_and_reads_are_counted_as_input_and_priced_apart(monkeypatch) -> None:
    install(monkeypatch, usage_message(recorded("insight_sells_services"), 4000, 0))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")
    written = await client.complete(request())

    install(monkeypatch, usage_message(recorded("insight_sells_services"), 0, 4000))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")
    read = await client.complete(request())

    assert written.input_tokens == read.input_tokens == 4050
    assert written.cost_eur == pytest.approx((50 * 3 + 4000 * 3 * 1.25 + 10 * 15) / 1e6)
    assert read.cost_eur == pytest.approx((50 * 3 + 4000 * 3 * 0.1 + 10 * 15) / 1e6)


@pytest.mark.asyncio(loop_scope="session")
async def test_one_connection_pool_serves_every_call_and_keeps_idle_connections(
    monkeypatch,
) -> None:
    seen = install(monkeypatch, message(recorded("insight_sells_services")))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")

    for _ in range(3):
        await client.complete(request())

    assert len(seen) == 3
    (options,) = install.pools  # type: ignore[attr-defined]
    assert options["limits"].keepalive_expiry == claude.KEEPALIVE_SECONDS
    assert client._client._client is client._http


@pytest.mark.asyncio(loop_scope="session")
async def test_warm_up_takes_the_token_and_opens_a_connection_without_a_model_call(
    monkeypatch,
) -> None:
    seen = install(monkeypatch, message(recorded("insight_sells_services")))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")

    await client.warm()

    (sent,) = seen
    assert (sent.method, str(sent.url)) == ("GET", BASE_URL)
    assert "authorization" not in sent.headers
    assert install.tokens == [TOKEN]  # type: ignore[attr-defined]


@pytest.mark.asyncio(loop_scope="session")
async def test_empty_values_claude_writes_for_unset_optional_properties_are_removed(
    monkeypatch,
) -> None:
    # A live answer shape: structured outputs keep optional properties optional, and Claude
    # wrote empty strings for the ones it meant to leave out.
    written = {
        "intents": [
            {
                "kind": "rel",
                "subject": {"candidate": "c1"},
                "object": {"newLabel": "Staff"},
                "action": "has",
                "confidence": 0.9,
                "explanation": "",
                "span": "wages have staff",
                "source": {"start": 0, "end": 16},
                "members": [{"newLabel": "Clerks"}],
                "memberAction": "",
            }
        ],
        "unresolved": [],
    }
    jsonschema.Draft202012Validator(OUTPUT_SCHEMA).validate(written)
    with pytest.raises(ValueError):
        TeachExtractionAnswer.model_validate(written)
    install(monkeypatch, message(json.dumps(written)))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5", PRICE, "none")

    answer = await client.complete(request())

    (intent,) = json.loads(answer.text)["intents"]
    assert "memberAction" not in intent and "explanation" not in intent
    assert json.loads(answer.text)["unresolved"] == []
    TeachExtractionAnswer.model_validate_json(answer.text)
