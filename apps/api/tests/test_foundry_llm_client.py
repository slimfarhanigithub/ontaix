"""The Azure AI Foundry adapter over an in-memory HTTP transport and a fake Entra ID credential.

No network call is made and no real credential is used: the token is a made-up value the tests
check never reaches a log, a response or a table.
"""

from __future__ import annotations

import asyncio
import functools
import io
import json
import logging
import time
import traceback
from decimal import Decimal

import httpx2
import jsonschema
import openai
import pytest
from azure.core.exceptions import ClientAuthenticationError
from sqlalchemy import text

import app.clients.foundry_llm_client as foundry
import app.clients.llm_client as llm_client
from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.clients import db_client
from app.clients.foundry_llm_client import FoundryLlmClient
from app.clients.llm_client import (
    LlmConfigurationError,
    LlmProviderError,
    LlmRequest,
    LlmTimeout,
    check_llm_configuration,
    reset_llm_client,
)
from app.clients.llm_log_redaction import redact
from app.config import ModelPrice, Settings, get_settings
from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from app.utilities.strict_json_schema import to_strict
from tests.conftest import TenantFixture
from tests.llm_fakes import recorded
from tests.test_teach_extraction import add_company, configure

ENDPOINT = "https://aif-ontaix-test-frc.openai.azure.com"
# A made-up value, not a credential: the tests check it never leaves the adapter.
TOKEN = "eyJfake.TOKENDUMMY.sig"
PRICE = ModelPrice(inputEurPerMTok=Decimal("2"), outputEurPerMTok=Decimal("10"))
PRICE_TABLE = '{"gpt-6-sol": {"inputEurPerMTok": 2, "outputEurPerMTok": 10}}'
PROMPT_TOKENS = 900
COMPLETION_TOKENS = 150
REASONING_TOKENS = 40


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.buf = io.StringIO()

    def emit(self, record: logging.LogRecord) -> None:
        self.buf.write(self.format(record) + "\n")
        if record.exc_info:
            self.buf.write("".join(traceback.format_exception(*record.exc_info)))


@pytest.fixture
def captured_logs():
    capture = _Capture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    names = ("openai", "openai._base_client", "azure", "httpx2", "httpcore")
    for name in names:
        logging.getLogger(name).addHandler(capture)
    try:
        yield capture.buf
    finally:
        root.removeHandler(capture)
        root.setLevel(old_level)
        for name in names:
            logging.getLogger(name).removeHandler(capture)


def strict_answer(name: str) -> str:
    """A recorded answer as strict mode writes it: every optional property present, null."""
    strict, _ = to_strict(OUTPUT_SCHEMA)
    answer = json.loads(recorded(name))
    for key in strict["properties"]:
        answer.setdefault(key, None)
    shapes = {
        k["properties"]["kind"]["enum"][0]: k["properties"]
        for k in strict["properties"]["intents"]["items"]["anyOf"]
    }
    for item in answer["intents"]:
        for key in shapes[item["kind"]]:
            item.setdefault(key, None)
    for item in answer["unresolved"]:
        for key in strict["properties"]["unresolved"]["items"]["properties"]:
            item.setdefault(key, None)
    return json.dumps(answer)


def completion(content: str, *, refusal: str | None = None, finish: str = "stop") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1790000000,
        "model": "gpt-6-sol-2026-09-22",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
        "usage": {
            "prompt_tokens": PROMPT_TOKENS,
            "completion_tokens": COMPLETION_TOKENS,
            "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
            "prompt_tokens_details": {"cached_tokens": 100},
            "completion_tokens_details": {"reasoning_tokens": REASONING_TOKENS},
        },
    }


def install(monkeypatch: pytest.MonkeyPatch, handler, token_provider=None) -> list:
    """Routes the SDK to `handler` and the credential to a fake; returns the requests seen."""
    seen: list[httpx2.Request] = []

    async def recording(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return await handler(request)

    async def fake_token() -> str:
        return TOKEN

    original = openai.AsyncOpenAI
    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        functools.partial(
            original, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(recording))
        ),
    )
    monkeypatch.setattr(foundry, "entra_token_provider", lambda: token_provider or fake_token)
    return seen


def adapter() -> FoundryLlmClient:
    return FoundryLlmClient(ENDPOINT, "gpt-6-sol", "gpt-6-sol", PRICE, "none")


def request(timeout: float = 5.0) -> LlmRequest:
    return LlmRequest(SYSTEM_PROMPT, '{"sentence": "x"}', OUTPUT_SCHEMA, MAX_OUTPUT_TOKENS, timeout)


def responding(body: dict, status: int = 200):
    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json=body)

    return handler


def test_the_strict_form_requires_every_property_and_keeps_the_answers_valid() -> None:
    strict, optional = to_strict(OUTPUT_SCHEMA)

    def objects(node):
        if isinstance(node, dict):
            if "properties" in node:
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    for node in objects(strict):
        assert node["required"] == list(node["properties"])
        assert node["additionalProperties"] is False
    assert {"rule", "domainKey", "segments", "segment"} <= optional
    assert "kind" not in optional and "candidate" not in optional
    jsonschema.Draft202012Validator(strict).validate(
        json.loads(strict_answer("services_offerings"))
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_a_recorded_structured_output_maps_to_the_answer(monkeypatch) -> None:
    seen = install(monkeypatch, responding(completion(strict_answer("insight_sells_services"))))

    answer = await adapter().complete(request())

    assert TeachExtractionAnswer.model_validate_json(
        answer.text
    ) == TeachExtractionAnswer.model_validate_json(recorded("insight_sells_services"))
    assert "null" not in answer.text
    assert (answer.input_tokens, answer.output_tokens) == (PROMPT_TOKENS, COMPLETION_TOKENS)
    assert answer.cost_eur == pytest.approx((PROMPT_TOKENS * 2 + COMPLETION_TOKENS * 10) / 1e6)
    (sent,) = seen
    assert sent.url.path == "/openai/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    assert "api-key" not in sent.headers
    body = json.loads(sent.content)
    assert body["model"] == "gpt-6-sol"
    assert body["max_completion_tokens"] == MAX_OUTPUT_TOKENS
    assert body["reasoning_effort"] == "none"
    assert body["store"] is False
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == to_strict(OUTPUT_SCHEMA)[0]
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_failed_status_is_one_attempt_and_a_provider_error(monkeypatch) -> None:
    seen = install(monkeypatch, responding({"error": {"message": "bad request"}}, status=400))

    with pytest.raises(LlmProviderError) as raised:
        await adapter().complete(request())

    assert str(raised.value) == "status" and len(seen) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_a_refusal_is_a_provider_error_with_its_usage(monkeypatch) -> None:
    install(monkeypatch, responding(completion("", refusal="I can't help with that.")))

    with pytest.raises(LlmProviderError) as raised:
        await adapter().complete(request())

    assert str(raised.value) == "refusal"
    assert (raised.value.input_tokens, raised.value.output_tokens) == (900, 150)


@pytest.mark.asyncio(loop_scope="session")
async def test_a_cut_off_answer_is_returned_as_is_for_validation(monkeypatch) -> None:
    install(monkeypatch, responding(completion('{"intents": [{"kind"', finish="length")))

    answer = await adapter().complete(request())

    assert answer.text == '{"intents": [{"kind"'


@pytest.mark.asyncio(loop_scope="session")
async def test_a_token_acquisition_failure_is_a_provider_error_and_logs_nothing(
    monkeypatch, captured_logs
) -> None:
    async def failing() -> str:
        raise ClientAuthenticationError(f"DefaultAzureCredential failed for tenant {TOKEN}")

    seen = install(monkeypatch, responding(completion("{}")), token_provider=failing)

    with pytest.raises(LlmProviderError) as raised:
        await adapter().complete(request())

    assert str(raised.value) == "credential" and seen == []
    assert "TOKENDUMMY" not in captured_logs.getvalue()
    assert raised.value.__cause__ is not None and "TOKENDUMMY" not in str(raised.value.__cause__)


@pytest.mark.asyncio(loop_scope="session")
async def test_slow_token_acquisition_is_a_timeout(monkeypatch) -> None:
    async def slow() -> str:
        await asyncio.sleep(5)
        return TOKEN

    install(monkeypatch, responding(completion("{}")), token_provider=slow)
    started = time.monotonic()

    with pytest.raises(LlmTimeout):
        await adapter().complete(request(timeout=0.3))

    assert time.monotonic() - started < 2.0


@pytest.mark.asyncio(loop_scope="session")
async def test_a_slow_provider_is_a_timeout(monkeypatch) -> None:
    async def slow(_: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200, json=completion("{}"))

    install(monkeypatch, slow)
    started = time.monotonic()

    with pytest.raises(LlmTimeout):
        await adapter().complete(request(timeout=0.3))

    assert time.monotonic() - started < 2.0


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("status", [200, 401, 500])
async def test_no_token_reaches_a_log(monkeypatch, captured_logs, status: int) -> None:
    body = completion(strict_answer("insight_sells_services")) if status == 200 else {}
    install(monkeypatch, responding(body, status=status))

    try:
        await adapter().complete(request())
    except LlmProviderError:
        pass

    assert "TOKENDUMMY" not in captured_logs.getvalue()


def test_the_redaction_masks_bearer_tokens_and_keys() -> None:
    masked = redact(f"headers {{'Authorization': 'Bearer {TOKEN}', 'api-key': 'abc123'}}")

    assert "TOKENDUMMY" not in masked and "abc123" not in masked
    assert "TOKENDUMMY" not in redact(f"token={TOKEN}")


def test_a_configured_provider_without_a_price_stops_start_up() -> None:
    settings = Settings(_env_file=None, foundry_endpoint=ENDPOINT, llm_model="unpriced")

    with pytest.raises(LlmConfigurationError):
        check_llm_configuration(settings)


def test_foundry_without_an_endpoint_starts_and_is_not_configured() -> None:
    settings = Settings(_env_file=None, llm_provider="azure_foundry", foundry_endpoint=None)

    check_llm_configuration(settings)
    assert llm_client._configured(settings, "live") is None


def test_an_unknown_provider_stops_start_up() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="openai")


@pytest.mark.asyncio(loop_scope="session")
async def test_settlement_counts_reasoning_tokens_as_output(
    client, tenant: TenantFixture, monkeypatch
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    monkeypatch.setenv("ONTAIX_LLM_PROVIDER", "azure_foundry")
    monkeypatch.setenv("ONTAIX_FOUNDRY_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("ONTAIX_LLM_MODEL", "gpt-6-sol")
    monkeypatch.setenv("ONTAIX_LLM_PRICE_TABLE", PRICE_TABLE)
    get_settings.cache_clear()
    install(monkeypatch, responding(completion(strict_answer("insight_sells_services"))))
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
    assert "TOKENDUMMY" not in r.text
    async with db_client.get_platform_session_factory()() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT provider, model, input_tokens, output_tokens, cost_eur"
                    " FROM ontaix.llm_call WHERE tenant_id = :t"
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
    ((provider, model, tokens_in, tokens_out, cost),) = rows
    assert (provider, model) == ("azure_foundry", "gpt-6-sol")
    # completion_tokens (150) includes the 40 reasoning tokens; they are counted once, as output.
    assert (tokens_in, tokens_out) == (PROMPT_TOKENS, COMPLETION_TOKENS)
    assert float(cost) == pytest.approx((PROMPT_TOKENS * 2 + COMPLETION_TOKENS * 10) / 1e6)
    assert int(month) == PROMPT_TOKENS + COMPLETION_TOKENS
