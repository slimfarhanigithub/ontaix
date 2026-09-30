"""POST /teach/parse/stream: drafts as the model's answer arrives, then the plain result.

Recorded model answers only, streamed by the fake client in small fragments; no test reaches a
provider.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth import Caller, get_caller
from app.clients import db_client
from app.clients.llm_client import (
    LlmAnswer,
    LlmRequest,
    LlmTimeout,
    TextListener,
    set_llm_client,
)
from app.models.api.teach import TeachRequest
from app.services import teach_service, teach_stream_service
from tests.conftest import TenantFixture
from tests.llm_fakes import INPUT_TOKENS, OUTPUT_TOKENS, FakeLlmClient, recorded
from tests.test_teach_extraction import FIRST, add_company, configure, rows
from tests.test_teach_grounding import OFFERINGS
from tests.test_teach_reuse import SENTENCE as SPLIT
from tests.test_teach_reuse import with_approved_services
from tests.test_teach_roles import SENTENCE as ADNOC
from tests.test_teach_speech import TRANSCRIPT, with_services

pytestmark = pytest.mark.asyncio(loop_scope="session")

Setup = Callable[[httpx.AsyncClient, TenantFixture], Awaitable[uuid.UUID]]


async def insight(client: httpx.AsyncClient, tenant: TenantFixture) -> uuid.UUID:
    company_id, _ = await add_company(tenant, "Insight")
    return company_id


async def pending_services(client: httpx.AsyncClient, tenant: TenantFixture) -> uuid.UUID:
    return await with_services(client, tenant)


async def approved_services(client: httpx.AsyncClient, tenant: TenantFixture) -> uuid.UUID:
    company_id, _ = await with_approved_services(client, tenant)
    return company_id


# Every recorded answer the teach tests use, with the sentence and the model it was taught to.
CASES: list[tuple[str, str, str, Setup]] = [
    ("insight_sells_services", "text", FIRST, insight),
    ("adnoc_client_subsidiaries", "text", ADNOC, insight),
    ("speech_adnoc_client_subsidiaries", "speech", ADNOC, insight),
    ("speech_insight_transcript", "speech", TRANSCRIPT, insight),
    ("speech_offsets_off_by_one", "speech", OFFERINGS, insight),
    ("services_offerings", "text", "Services has 3 offerings, APPS, Data and AI", pending_services),
    (
        "services_offerings_count_mismatch",
        "text",
        "Services has 2 offerings, APPS, Data and AI",
        pending_services,
    ),
    (
        "speech_services_offerings",
        "speech",
        "Services has 3 offerings, APPS, Data and AI.",
        pending_services,
    ),
    ("insight_has_services_split", "text", SPLIT, approved_services),
    ("speech_insight_has_services_split", "speech", SPLIT, approved_services),
]


def body(company_id: uuid.UUID, sentence: str, origin: str = "text") -> dict:
    return {"companyId": str(company_id), "text": sentence, "origin": origin}


async def plain(client: httpx.AsyncClient, tenant: TenantFixture, request: dict) -> dict:
    response = await client.post("/teach/parse", json=request, headers=tenant.builder.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def streamed(client: httpx.AsyncClient, tenant: TenantFixture, request: dict) -> list[dict]:
    response = await client.post(
        "/teach/parse/stream", json=request, headers=tenant.builder.headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.headers["cache-control"] == "no-store"
    assert response.text.endswith("\n")
    return [json.loads(line) for line in response.text.splitlines()]


def standing(events: list[dict]) -> list[dict]:
    """The streamed drafts no retract line names, in the order they were sent."""
    retracted = {i for e in events if e["type"] == "retract" for i in e["indexes"]}
    return [e["draft"] for e in events if e["type"] == "draft" and e["index"] not in retracted]


@pytest.mark.parametrize(("name", "origin", "sentence", "setup"), CASES)
async def test_the_stream_ends_with_the_plain_result_and_streams_its_drafts(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    name: str,
    origin: str,
    sentence: str,
    setup: Setup,
) -> None:
    company_id = await setup(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded(name), recorded(name))
    request = body(company_id, sentence, origin)

    expected = await plain(client, tenant, request)
    events = await streamed(client, tenant, request)

    assert fake_llm.streamed == 1
    assert events[-1] == {"type": "result", "result": expected}
    assert [e["type"] for e in events[:-1]] == ["draft"] * (len(events) - 1)
    assert [e["index"] for e in events[:-1]] == list(range(len(events) - 1))
    assert expected["llmOutcome"] == "used" and expected["drafts"]
    # Each answer's drafts are known intent by intent, so every one of them is streamed.
    assert standing(events) == expected["drafts"]
    notes = [e["note"] for e in events[:-1]]
    assert [n["extractor"] for n in notes] == [n["extractor"] for n in expected["draftNotes"]]


async def test_a_draft_is_sent_before_the_answer_ends(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    answer = recorded("adnoc_client_subsidiaries")
    end_of_first = '"memberAction": "includes"}'
    first_closed = answer.index(end_of_first) + len(end_of_first)
    released = asyncio.Event()
    held_at: list[int] = []

    class Gated(FakeLlmClient):
        async def stream(self, request: LlmRequest, on_text: TextListener) -> LlmAnswer:
            await on_text(answer[:first_closed])
            held_at.append(first_closed)
            await released.wait()
            await on_text(answer)
            return LlmAnswer(answer, INPUT_TOKENS, OUTPUT_TOKENS, 0.002, 420)

    set_llm_client(Gated())
    async with db_client.get_session_factory()() as session:
        caller = await _caller(session, tenant)
        prepared = await teach_service.prepare(
            session, caller, TeachRequest.model_validate(body(company_id, ADNOC))
        )
        await session.commit()
    lines = teach_stream_service.events(prepared)

    first = json.loads(await anext(lines))

    assert held_at == [first_closed] and not released.is_set()
    assert first["type"] == "draft" and first["draft"]["label"] == "Client"
    released.set()
    rest = [json.loads(line) async for line in lines]
    assert rest[-1]["type"] == "result"
    assert standing([first, *rest]) == rest[-1]["result"]["drafts"]


async def test_a_refused_answer_retracts_every_streamed_draft(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    answer = json.loads(recorded("insight_sells_services"))
    # A second intent the whole-answer checks refuse: an action of `is a`.
    looped = {**answer["intents"][0], "action": "is a"}
    refused = json.dumps({**answer, "intents": [answer["intents"][0], looped]}, indent=2)
    fake_llm.answer(refused, refused)
    request = body(company_id, FIRST)

    expected = await plain(client, tenant, request)
    events = await streamed(client, tenant, request)

    assert (expected["llmOutcome"], expected["outcome"], expected["drafts"]) == (
        "invalid_output",
        "not_understood",
        [],
    )
    drafts = [e for e in events if e["type"] == "draft"]
    assert [d["draft"]["label"] for d in drafts] == ["Services"]
    assert events[-2] == {"type": "retract", "indexes": [0]}
    assert events[-1] == {"type": "result", "result": expected}


async def test_notes_the_whole_answer_completes_come_with_the_result_and_the_drafts_stand(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await pending_services(client, tenant)
    await configure(tenant)
    sentence = "Services has 2 offerings, APPS, Data and AI"
    answer = recorded("services_offerings_count_mismatch")
    fake_llm.answer(answer, answer)
    fake_llm.fragment = 3
    request = body(company_id, sentence)

    expected = await plain(client, tenant, request)
    events = await streamed(client, tenant, request)

    assert events[-1] == {"type": "result", "result": expected}
    assert standing(events) == expected["drafts"]


async def test_a_retried_attempt_starts_the_reading_again_without_repeating_drafts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    answer = recorded("adnoc_client_subsidiaries")
    fake_llm.answer(answer, answer)
    fake_llm.restart_at = len(answer) // 2
    request = body(company_id, ADNOC)

    expected = await plain(client, tenant, request)
    events = await streamed(client, tenant, request)

    assert events[-1] == {"type": "result", "result": expected}
    drafts = [e["draft"] for e in events if e["type"] == "draft"]
    assert drafts == expected["drafts"]


async def test_the_stream_spends_the_same_budget_and_writes_the_same_cost_row(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded("insight_sells_services"), recorded("insight_sells_services"))
    request = body(company_id, FIRST)

    await plain(client, tenant, request)
    await streamed(client, tenant, request)

    calls = await rows(
        "SELECT outcome, input_tokens, output_tokens, cost_eur, purpose FROM ontaix.llm_call"
        " WHERE tenant_id = :t ORDER BY occurred_at",
        t=tenant.tenant_id,
    )
    assert len(calls) == 2 and calls[0] == calls[1]
    assert (calls[1]["outcome"], calls[1]["input_tokens"], calls[1]["output_tokens"]) == (
        "used",
        INPUT_TOKENS,
        OUTPUT_TOKENS,
    )
    [window] = await rows(
        "SELECT spent FROM ontaix.rate_budget_window WHERE tenant_id = :t AND budget = 'llm'",
        t=tenant.tenant_id,
    )
    assert window["spent"] == 2
    [usage] = await rows(
        "SELECT tokens FROM ontaix.llm_month_usage WHERE tenant_id = :t", t=tenant.tenant_id
    )
    assert usage["tokens"] == 2 * (INPUT_TOKENS + OUTPUT_TOKENS)


async def test_an_exhausted_budget_and_a_timeout_stream_no_draft(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    fake_llm.answer(LlmTimeout("timeout", latency_ms=15_000))

    timed_out = await streamed(client, tenant, body(company_id, FIRST))
    await configure(tenant, llm_monthly_token_cap=500)
    exhausted = await streamed(client, tenant, body(company_id, FIRST))

    for events, outcome in ((timed_out, "timeout"), (exhausted, "budget_exhausted")):
        assert [e["type"] for e in events] == ["result"]
        assert events[0]["result"]["llmOutcome"] == outcome
        assert events[0]["result"]["degraded"] is True


async def test_a_sentence_without_a_model_step_streams_its_result_alone(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    await configure(tenant, llm_monthly_token_cap=0)
    request = body(tenant.company_id, "A plant has machines")

    expected = await plain(client, tenant, request)
    events = await streamed(client, tenant, request)

    assert events == [{"type": "result", "result": expected}]
    assert fake_llm.requests == []


async def test_refusals_answer_before_the_stream_begins(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    unknown = await client.post(
        "/teach/parse/stream",
        json=body(uuid.uuid4(), FIRST),
        headers=tenant.builder.headers,
    )
    await configure(tenant, voice=False)
    spoken = await client.post(
        "/teach/parse/stream",
        json=body(tenant.company_id, FIRST, "speech"),
        headers=tenant.builder.headers,
    )
    invalid = await client.post(
        "/teach/parse/stream",
        json={"companyId": str(tenant.company_id)},
        headers=tenant.builder.headers,
    )

    assert (unknown.status_code, unknown.json()["code"]) == (404, "not_found")
    assert (spoken.status_code, spoken.json()["code"]) == (409, "channel_disabled")
    assert (invalid.status_code, invalid.json()["code"]) == (422, "validation_failed")
    assert fake_llm.requests == []


async def test_a_parse_failing_after_the_stream_began_ends_with_an_error_line(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = await insight(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded("insight_sells_services"))

    def broken(*_: object) -> list:
        raise RuntimeError("turns")

    monkeypatch.setattr(teach_service, "_turns", broken)
    events = await streamed(client, tenant, body(company_id, FIRST))

    assert [e["type"] for e in events] == ["draft", "error"]
    assert events[-1]["problem"]["code"] == "unavailable"
    assert events[-1]["problem"]["status"] == 503


async def _caller(session: AsyncSession, tenant: TenantFixture) -> Caller:
    """The builder as the API resolves it from a request."""
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in tenant.builder.headers.items()],
    }
    return await get_caller(Request(scope), session)
