"""Bounded retries of 429 and 503 from the model provider, over in-memory HTTP transports.

Both SDK call paths - the Foundry OpenAI client and the Anthropic client used for Claude on
Foundry - go through the same retry policy; these tests drive each with scripted responses.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import time
from datetime import UTC, datetime, timedelta

import anthropic
import httpx2
import pytest
from sqlalchemy import text

import app.clients.anthropic_foundry_llm_client as claude
import app.clients.llm_client as llm_client
import app.clients.llm_retry as llm_retry
from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.clients import db_client
from app.clients.anthropic_foundry_llm_client import AnthropicFoundryLlmClient
from app.clients.llm_client import LlmProviderError, LlmRequest, LlmTimeout, reset_llm_client
from app.clients.llm_retry import retry_after_seconds, retry_wait
from app.config import get_settings
from evals import recording_llm_client
from evals.recording_llm_client import Budget, CallGate, RecordingLlmClient, record_calls
from tests.conftest import TenantFixture
from tests.test_anthropic_foundry_llm_client import BASE_URL, message
from tests.test_anthropic_foundry_llm_client import PRICE as CLAUDE_PRICE
from tests.test_foundry_llm_client import (
    COMPLETION_TOKENS,
    ENDPOINT,
    PRICE_TABLE,
    PROMPT_TOKENS,
    adapter,
    completion,
    install,
    strict_answer,
)
from tests.test_teach_extraction import add_company, configure

ANSWER = "insight_sells_services"
THROTTLED = {"error": {"code": "429", "message": "Rate limit is exceeded."}}
UNAVAILABLE = {"error": {"code": "503", "message": "Service unavailable."}}


@pytest.fixture(autouse=True)
def quick_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff waits of a few milliseconds, so tests without a hint stay fast."""
    monkeypatch.setattr(llm_retry, "BACKOFF_BASE_SECONDS", 0.01)
    monkeypatch.setattr(llm_retry, "BACKOFF_CAP_SECONDS", 0.02)
    monkeypatch.setattr(llm_retry, "MIN_ATTEMPT_SECONDS", 0.2)


def scripted(*responses: tuple[int, dict, dict[str, str]]):
    """A handler answering each request with the next response; the last one repeats."""
    queue = list(responses)

    async def handler(_: httpx2.Request) -> httpx2.Response:
        status, body, headers = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx2.Response(status, json=body, headers=headers)

    return handler


def answered() -> tuple[int, dict, dict[str, str]]:
    return 200, completion(strict_answer(ANSWER)), {}


def request(timeout: float = 5.0) -> LlmRequest:
    return LlmRequest(SYSTEM_PROMPT, '{"sentence": "x"}', OUTPUT_SCHEMA, MAX_OUTPUT_TOKENS, timeout)


@pytest.mark.asyncio(loop_scope="session")
async def test_a_429_then_an_answer_returns_the_answer_with_its_tokens(monkeypatch, caplog) -> None:
    seen = install(monkeypatch, scripted((429, THROTTLED, {}), answered()))
    caplog.set_level(logging.DEBUG, logger="app.clients.llm_retry")

    answer = await adapter().complete(request())

    assert len(seen) == 2
    assert (answer.input_tokens, answer.output_tokens) == (PROMPT_TOKENS, COMPLETION_TOKENS)
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert len(infos) == 1 and infos[0].startswith("language model call answered 429; retry 1")
    assert any("attempt 2 answered after" in r.getMessage() for r in caplog.records)
    assert all("sentence" not in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio(loop_scope="session")
async def test_three_429s_end_as_the_rate_limited_provider_error(monkeypatch) -> None:
    seen = install(monkeypatch, scripted((429, THROTTLED, {})))

    with pytest.raises(LlmProviderError) as raised:
        await adapter().complete(request())

    assert len(seen) == 1 + llm_retry.MAX_RETRIES == 3
    assert str(raised.value) == "status"
    assert raised.value.__cause__.status_code == 429  # type: ignore[union-attr]
    assert recording_llm_client._rate_limited(raised.value)
    assert (raised.value.input_tokens, raised.value.output_tokens, raised.value.cost_eur) == (
        0,
        0,
        0.0,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_a_503_is_retried_like_a_429(monkeypatch) -> None:
    seen = install(monkeypatch, scripted((503, UNAVAILABLE, {}), answered()))

    answer = await adapter().complete(request())

    assert len(seen) == 2 and answer.input_tokens == PROMPT_TOKENS


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_other_4xx_statuses_are_one_attempt(monkeypatch, status: int) -> None:
    seen = install(monkeypatch, scripted((status, {"error": {"message": "no"}}, {})))

    with pytest.raises(LlmProviderError) as raised:
        await adapter().complete(request())

    assert len(seen) == 1 and str(raised.value) == "status"


@pytest.mark.asyncio(loop_scope="session")
async def test_retry_after_ms_is_honoured(monkeypatch) -> None:
    seen = install(monkeypatch, scripted((429, THROTTLED, {"retry-after-ms": "300"}), answered()))
    started = time.monotonic()

    await adapter().complete(request())

    assert len(seen) == 2 and time.monotonic() - started >= 0.3


@pytest.mark.asyncio(loop_scope="session")
async def test_a_long_retry_after_is_capped(monkeypatch) -> None:
    monkeypatch.setattr(llm_retry, "RETRY_AFTER_CAP_SECONDS", 0.05)
    seen = install(monkeypatch, scripted((429, THROTTLED, {"retry-after": "60"}), answered()))
    started = time.monotonic()

    await adapter().complete(request())

    assert len(seen) == 2 and time.monotonic() - started < 1.0


def test_the_wait_reads_both_hints_and_backs_off_with_jitter_without_one() -> None:
    later = email.utils.format_datetime(datetime.now(UTC) + timedelta(seconds=3), usegmt=True)

    assert retry_after_seconds({"retry-after-ms": "250", "retry-after": "9"}) == 0.25
    assert retry_after_seconds({"retry-after": "2"}) == 2.0
    assert 1.0 < retry_after_seconds({"retry-after": later}) <= 3.0  # type: ignore[operator]
    assert retry_after_seconds({"retry-after": "soon"}) is None
    assert retry_after_seconds({}) is None
    assert retry_wait({"retry-after": "2"}, 0) == min(2.0, llm_retry.RETRY_AFTER_CAP_SECONDS)
    assert retry_wait({"retry-after": "3600"}, 0) == llm_retry.RETRY_AFTER_CAP_SECONDS
    base, cap = llm_retry.BACKOFF_BASE_SECONDS, llm_retry.BACKOFF_CAP_SECONDS
    for retries in range(4):
        ceiling = min(cap, base * 2**retries)
        assert ceiling / 2 <= retry_wait({}, retries) <= ceiling


@pytest.mark.asyncio(loop_scope="session")
async def test_no_retry_is_made_when_its_wait_would_pass_the_timeout(monkeypatch) -> None:
    seen = install(monkeypatch, scripted((429, THROTTLED, {"retry-after": "1"}), answered()))
    monkeypatch.setattr(llm_retry, "RETRY_AFTER_CAP_SECONDS", 4.0)
    started = time.monotonic()

    with pytest.raises(LlmProviderError):
        await adapter().complete(request(timeout=1.0))

    assert len(seen) == 1 and time.monotonic() - started < 0.5


@pytest.mark.asyncio(loop_scope="session")
async def test_a_retry_stays_within_the_call_timeout(monkeypatch) -> None:
    calls = 0

    async def throttled_then_slow(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(429, json=THROTTLED, headers={"retry-after-ms": "50"})
        await asyncio.sleep(5)
        return httpx2.Response(200, json=completion("{}"))

    install(monkeypatch, throttled_then_slow)
    started = time.monotonic()

    with pytest.raises(LlmTimeout):
        await adapter().complete(request(timeout=0.8))

    assert calls == 2 and time.monotonic() - started < 1.3


def claude_install(monkeypatch: pytest.MonkeyPatch, handler) -> list:
    seen: list[httpx2.Request] = []

    async def recording(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return await handler(request)

    async def fake_token() -> str:
        return "eyJfake.CLAUDE.sig"

    monkeypatch.setattr(
        anthropic,
        "DefaultAsyncHttpxClient",
        lambda **options: httpx2.AsyncClient(transport=httpx2.MockTransport(recording), **options),
    )
    monkeypatch.setattr(claude, "entra_token_provider", lambda: fake_token)
    return seen


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("status", [429, 503])
async def test_claude_retries_429_and_503_then_answers(monkeypatch, status: int) -> None:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    seen = claude_install(
        monkeypatch, scripted((status, body, {}), (200, message('{"intents": []}'), {}))
    )
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", CLAUDE_PRICE, "medium")

    answer = await client.complete(request())

    assert len(seen) == 2 and (answer.input_tokens, answer.output_tokens) == (800, 300)


@pytest.mark.asyncio(loop_scope="session")
async def test_claude_stops_after_two_retries_and_does_not_retry_a_400(monkeypatch) -> None:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    seen = claude_install(monkeypatch, scripted((429, body, {})))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", CLAUDE_PRICE, "medium")

    with pytest.raises(LlmProviderError) as raised:
        await client.complete(request())

    assert len(seen) == 3 and raised.value.__cause__.status_code == 429  # type: ignore[union-attr]

    seen = claude_install(monkeypatch, scripted((400, body, {})))
    client = AnthropicFoundryLlmClient(BASE_URL, "claude-sonnet-5-5", CLAUDE_PRICE, "medium")
    with pytest.raises(LlmProviderError):
        await client.complete(request())
    assert len(seen) == 1


async def _teach_once(client, tenant: TenantFixture, monkeypatch, handler) -> list:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    monkeypatch.setenv("ONTAIX_LLM_PROVIDER", "azure_foundry")
    monkeypatch.setenv("ONTAIX_FOUNDRY_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("ONTAIX_LLM_MODEL", "gpt-6-sol")
    monkeypatch.setenv("ONTAIX_LLM_PRICE_TABLE", PRICE_TABLE)
    get_settings.cache_clear()
    seen = install(monkeypatch, handler)
    monkeypatch.setattr(llm_client, "_cached", {})
    reset_llm_client()
    try:
        r = await client.post(
            "/teach/parse",
            json={"companyId": str(company_id), "text": "these services sell stuff"},
            headers=tenant.builder.headers,
        )
    finally:
        get_settings.cache_clear()
    assert r.status_code == 200, r.text
    return seen


async def _accounting(tenant: TenantFixture) -> tuple[list, int]:
    async with db_client.get_platform_session_factory()() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT outcome, input_tokens, output_tokens FROM ontaix.llm_call"
                    " WHERE tenant_id = :t"
                ),
                {"t": tenant.tenant_id},
            )
        ).all()
        month = (
            await s.execute(
                text(
                    "SELECT coalesce(sum(tokens), 0) FROM ontaix.llm_month_usage"
                    " WHERE tenant_id = :t"
                ),
                {"t": tenant.tenant_id},
            )
        ).scalar_one()
    return [tuple(r) for r in rows], int(month)


@pytest.mark.asyncio(loop_scope="session")
async def test_a_retried_call_is_one_reservation_one_record_and_charged_once(
    client, tenant: TenantFixture, monkeypatch
) -> None:
    seen = await _teach_once(
        client, tenant, monkeypatch, scripted((429, THROTTLED, {}), answered())
    )

    rows, month = await _accounting(tenant)
    assert len(seen) == 2
    assert rows == [("used", PROMPT_TOKENS, COMPLETION_TOKENS)]
    assert month == PROMPT_TOKENS + COMPLETION_TOKENS


@pytest.mark.asyncio(loop_scope="session")
async def test_a_call_rate_limited_throughout_releases_its_whole_reservation(
    client, tenant: TenantFixture, monkeypatch
) -> None:
    seen = await _teach_once(client, tenant, monkeypatch, scripted((429, THROTTLED, {})))

    rows, month = await _accounting(tenant)
    assert len(seen) == 3
    assert rows == [("provider_error", 0, 0)]
    assert month == 0


class _Throttled(Exception):
    status_code = 429


class _Inner:
    provider = "fake"
    model = "fake"

    def __init__(self, refusals: int) -> None:
        self.refusals = refusals
        self.active = 0
        self.peak = 0

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return 1

    async def complete(self, request: LlmRequest) -> llm_client.LlmAnswer:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            if self.refusals:
                self.refusals -= 1
                raise LlmProviderError("status") from _Throttled()
            return llm_client.LlmAnswer("{}", 10, 5, 0.001, 3)
        finally:
            self.active -= 1


@pytest.mark.asyncio(loop_scope="session")
async def test_the_eval_gate_halves_concurrent_calls_on_each_429(monkeypatch) -> None:
    monkeypatch.setattr(recording_llm_client, "RATE_LIMIT_PAUSE_SECONDS", 0)
    inner = _Inner(refusals=2)
    gate = CallGate(4)
    client = RecordingLlmClient(inner, Budget(1.0), gate)

    async def one() -> None:
        record_calls()
        await client.complete(LlmRequest("s", "u", {}, 10, 1.0))

    await asyncio.gather(*(one() for _ in range(8)))

    assert gate.limit == 1
    assert inner.peak <= 4
    inner.peak = 0
    await asyncio.gather(*(one() for _ in range(4)))
    assert inner.peak == 1
