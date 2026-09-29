"""Claude on Azure AI Foundry over an in-memory HTTP transport and a fake Entra ID token."""

from __future__ import annotations

import functools
import json
from decimal import Decimal

import anthropic
import httpx2
import pytest

import app.clients.anthropic_foundry_llm_client as claude
from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.clients.anthropic_foundry_llm_client import (
    AnthropicFoundryLlmClient,
    foundry_messages_url,
    thinking_options,
)
from app.clients.llm_client import LlmProviderError, LlmRequest
from app.config import ModelPrice
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

    async def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json=body)

    async def fake_token() -> str:
        return TOKEN

    original = anthropic.AsyncAnthropicFoundry
    monkeypatch.setattr(
        anthropic,
        "AsyncAnthropicFoundry",
        functools.partial(
            original, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        ),
    )
    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
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
    assert answer.cost_eur == pytest.approx((800 * 3 + 300 * 15) / 1e6)
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
