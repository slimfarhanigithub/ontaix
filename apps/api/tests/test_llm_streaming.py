"""Streamed calls of the Foundry and Claude adapters over in-memory server-sent events.

A streamed call gives the answer, the token counts and the refusals of the whole call, and hands
the text received so far to its listener after every fragment.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

import app.clients.anthropic_foundry_llm_client as claude
from app.clients.anthropic_foundry_llm_client import AnthropicFoundryLlmClient
from app.clients.llm_client import LlmProviderError
from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from tests.llm_fakes import recorded
from tests.test_anthropic_foundry_llm_client import BASE_URL, TOKEN
from tests.test_anthropic_foundry_llm_client import PRICE as CLAUDE_PRICE
from tests.test_anthropic_foundry_llm_client import request as claude_request
from tests.test_foundry_llm_client import (
    COMPLETION_TOKENS,
    PROMPT_TOKENS,
    adapter,
    install,
    request,
    strict_answer,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

FRAGMENT = 11


def sse(events: list[tuple[str | None, str]]) -> bytes:
    lines = []
    for name, data in events:
        if name is not None:
            lines.append(f"event: {name}")
        lines.append(f"data: {data}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode()


def pieces(text: str) -> list[str]:
    return [text[i : i + FRAGMENT] for i in range(0, len(text), FRAGMENT)]


def chunk(delta: dict, finish: str | None = None) -> str:
    return json.dumps(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1790000000,
            "model": "gpt-6-sol-2026-09-22",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
    )


def usage_chunk() -> str:
    return json.dumps(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1790000000,
            "model": "gpt-6-sol-2026-09-22",
            "choices": [],
            "usage": {
                "prompt_tokens": PROMPT_TOKENS,
                "completion_tokens": COMPLETION_TOKENS,
                "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
            },
        }
    )


def openai_stream(text: str, *, refusal: str | None = None, finish: str = "stop"):
    events: list[tuple[str | None, str]] = [(None, chunk({"role": "assistant", "content": ""}))]
    events += [(None, chunk({"content": piece})) for piece in pieces(text)]
    if refusal:
        events.append((None, chunk({"refusal": refusal})))
    events += [(None, chunk({}, finish)), (None, usage_chunk()), (None, "[DONE]")]
    body = sse(events)

    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    return handler


class Heard:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def __call__(self, text: str) -> None:
        self.texts.append(text)


async def test_a_streamed_foundry_answer_is_the_answer_of_the_whole_call(monkeypatch) -> None:
    raw = strict_answer("insight_sells_services")
    seen = install(monkeypatch, openai_stream(raw))
    heard = Heard()

    answer = await adapter().stream(request(), heard)

    assert TeachExtractionAnswer.model_validate_json(
        answer.text
    ) == TeachExtractionAnswer.model_validate_json(recorded("insight_sells_services"))
    assert "null" not in answer.text
    assert (answer.input_tokens, answer.output_tokens) == (PROMPT_TOKENS, COMPLETION_TOKENS)
    assert heard.texts == [raw[: i + FRAGMENT] for i in range(0, len(raw), FRAGMENT)]
    body = json.loads(seen[0].content)
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["response_format"]["json_schema"]["strict"] is True
    assert adapter().answer_text(raw, request()) == answer.text


async def test_a_streamed_refusal_or_content_filter_is_refused_with_its_usage(
    monkeypatch,
) -> None:
    install(monkeypatch, openai_stream("", refusal="I can't help with that."))
    with pytest.raises(LlmProviderError) as refused:
        await adapter().stream(request(), Heard())

    install(monkeypatch, openai_stream('{"intents": [', finish="content_filter"))
    with pytest.raises(LlmProviderError) as filtered:
        await adapter().stream(request(), Heard())

    for raised in (refused, filtered):
        assert str(raised.value) == "refusal"
        assert (raised.value.input_tokens, raised.value.output_tokens) == (900, 150)


async def test_a_rate_limited_stream_is_retried_and_its_text_starts_again(monkeypatch) -> None:
    raw = strict_answer("insight_sells_services")
    answered = openai_stream(raw)
    calls: list[int] = []

    async def handler(request_: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                429, json={"error": {"message": "busy"}}, headers={"retry-after-ms": "10"}
            )
        return await answered(request_)

    install(monkeypatch, handler)
    heard = Heard()

    answer = await adapter().stream(request(), heard)

    assert len(calls) == 2
    assert heard.texts[-1] == raw and answer.output_tokens == COMPLETION_TOKENS


def claude_events(text: str, stop: str = "end_turn") -> bytes:
    start = {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 700,
                "output_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 100,
            },
        },
    }
    events: list[tuple[str | None, str]] = [("message_start", json.dumps(start))]
    events.append(
        (
            "content_block_start",
            json.dumps(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }
            ),
        )
    )
    for piece in pieces(text):
        delta = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": piece},
        }
        events.append(("content_block_delta", json.dumps(delta)))
    events.append(("content_block_stop", json.dumps({"type": "content_block_stop", "index": 0})))
    end = {
        "type": "message_delta",
        "delta": {"stop_reason": stop, "stop_sequence": None},
        "usage": {"output_tokens": 300},
    }
    events.append(("message_delta", json.dumps(end)))
    events.append(("message_stop", json.dumps({"type": "message_stop"})))
    return sse(events)


def install_claude(monkeypatch: pytest.MonkeyPatch, body: bytes) -> list[httpx2.Request]:
    seen: list[httpx2.Request] = []

    async def handler(request_: httpx2.Request) -> httpx2.Response:
        seen.append(request_)
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    def pool(**options: object) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **options)

    async def fake_token() -> str:
        return TOKEN

    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", pool)
    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
    return seen


async def test_a_streamed_claude_answer_counts_every_token_as_the_whole_call(
    monkeypatch,
) -> None:
    raw = recorded("insight_sells_services")
    seen = install_claude(monkeypatch, claude_events(raw))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", CLAUDE_PRICE, "medium")
    heard = Heard()

    answer = await client.stream(claude_request(), heard)

    assert json.loads(answer.text) == json.loads(raw)
    assert (answer.input_tokens, answer.output_tokens) == (800, 300)
    assert answer.cost_eur == pytest.approx((700 * 3 + 100 * 3 * 0.1 + 300 * 15) / 1e6)
    assert heard.texts[-1] == raw and len(heard.texts) == len(pieces(raw))
    body = json.loads(seen[0].content)
    assert body["stream"] is True
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["output_config"]["format"]["type"] == "json_schema"


async def test_a_streamed_claude_refusal_is_refused(monkeypatch) -> None:
    install_claude(monkeypatch, claude_events("", stop="refusal"))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", CLAUDE_PRICE, "low")

    with pytest.raises(LlmProviderError) as refused:
        await client.stream(claude_request(), Heard())

    assert str(refused.value) == "refusal"
