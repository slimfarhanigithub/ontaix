"""The streamed parse shows the grammar's drafts at once and matches drafts by concept.

A typed sentence the grammar reads whole streams the grammar's drafts before the model
answers; the model's result replaces them, and a draft the model refines (another action or
domain for the same concept) keeps the cell already shown. Recorded model answers only.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.clients import db_client
from app.clients.llm_client import LlmAnswer, LlmRequest, TextListener, set_llm_client
from app.models.api.teach import TeachRequest
from app.services import teach_service, teach_stream_service
from app.services.teach_stream_service import same_draft, unmatched
from tests.conftest import TenantFixture
from tests.llm_fakes import INPUT_TOKENS, OUTPUT_TOKENS, FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_roles import SENTENCE as ADNOC
from tests.test_teach_stream import _caller, body, standing, streamed

pytestmark = pytest.mark.asyncio(loop_scope="session")

SENTENCE = "Insight has services"
TWO = "Insight has services and products"


def model_answer(label: str, action: str, domain: str = "sales", sentence: str = SENTENCE) -> str:
    return json.dumps(
        {
            "intents": [
                {
                    "kind": "rel",
                    "subject": {"candidate": "c0"},
                    "object": {"newLabel": label},
                    "action": action,
                    "domainKey": domain,
                    "confidence": 0.95,
                    "span": sentence,
                    "source": {"start": 0, "end": len(sentence)},
                }
            ],
            "unresolved": [],
        }
    )


async def test_the_grammars_drafts_are_streamed_before_the_model_answers(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    released = asyncio.Event()

    class Held(FakeLlmClient):
        async def stream(self, request: LlmRequest, on_text: TextListener) -> LlmAnswer:
            await released.wait()
            answer = model_answer("Services", "has", "production")
            await on_text(answer)
            return LlmAnswer(answer, INPUT_TOKENS, OUTPUT_TOKENS, 0.002, 420)

    set_llm_client(Held())
    async with db_client.get_session_factory()() as session:
        caller = await _caller(session, tenant)
        prepared = await teach_service.prepare(
            session, caller, TeachRequest.model_validate(body(company_id, SENTENCE))
        )
        await session.commit()
    lines = teach_stream_service.events(prepared)

    first = json.loads(await anext(lines))

    assert not released.is_set()
    assert first["type"] == "draft" and first["note"]["extractor"] == "rules"
    assert (first["draft"]["label"], first["draft"]["parentId"]) == ("Service", str(root_id))
    released.set()
    rest = [json.loads(line) async for line in lines]
    result = rest[-1]["result"]
    # The model's draft names the same concept: no second draft line, no retraction, and the
    # result carries the model's draft, never the grammar's.
    assert [e["type"] for e in rest] == ["result"]
    assert [d["label"] for d in result["drafts"]] == ["Services"]
    assert result["draftNotes"][0]["extractor"] == "llm"
    assert same_draft(first["draft"], result["drafts"][0])


async def test_a_grammar_draft_the_model_does_not_confirm_is_retracted(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    # The grammar reads `Service` and `Product`; the model names `Products` alone, so the
    # first preview is retracted and the second is the model's concept, refined.
    fake_llm.answer(model_answer("Products", "offers", sentence=TWO))

    events = await streamed(client, tenant, body(company_id, TWO))

    kinds = [e["type"] for e in events]
    assert kinds == ["draft", "draft", "retract", "result"]
    assert [e["note"]["extractor"] for e in events[:2]] == ["rules", "rules"]
    assert [e["draft"]["label"] for e in events[:2]] == ["Service", "Product"]
    assert [d["label"] for d in events[-1]["result"]["drafts"]] == ["Products"]
    assert events[2]["indexes"] == [0]
    [kept] = standing(events)
    assert same_draft(kept, events[-1]["result"]["drafts"][0])


async def test_a_reading_the_grammar_gets_wrong_streams_no_instant_draft(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    from tests.llm_fakes import recorded

    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(recorded("adnoc_client_subsidiaries"))

    events = await streamed(client, tenant, body(company_id, ADNOC))

    assert all(e["note"]["extractor"] == "llm" for e in events if e["type"] == "draft")
    assert events[0]["draft"]["label"] == "Client"


def test_drafts_of_one_concept_are_the_same_whatever_their_action_or_number() -> None:
    early = {
        "type": "concept",
        "companyId": "x",
        "parentId": "r",
        "label": "Service",
        "action": "has",
    }
    refined = {**early, "label": "Services", "action": "sells", "domainKey": "sales"}
    other = {**early, "label": "Products"}
    elsewhere = {**early, "parentId": "q"}
    relation = {"type": "relation", "companyId": "x", "aId": "r", "bId": "s", "action": "has"}

    assert same_draft(early, refined) and same_draft(early, early)
    assert not same_draft(early, other) and not same_draft(early, elsewhere)
    assert not same_draft(relation, {**relation, "action": "sells"})
    assert unmatched([refined, other], [early]) == [1]
    assert unmatched([early], [refined, other]) == []
