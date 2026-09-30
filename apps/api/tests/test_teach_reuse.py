"""Teaching around what the model already holds: existing concepts are reused and a restated
relation is kept as a statement without a draft, so the new facts of the sentence are proposed.

Recorded model answers only; the two `insight_has_services_split` fixtures are the provider's
answers to the owner's sentence.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.services import teach_extraction_service
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient, recorded
from tests.test_teach_extraction import add_company, configure, teach
from tests.test_teach_speech import speak, submit

pytestmark = pytest.mark.asyncio(loop_scope="session")

SENTENCE = "Insight has services, they are split into AI, Data and Apps."
KNOWN = "Insight has Services (already in the model)"


async def with_approved_services(
    client: httpx.AsyncClient, tenant: TenantFixture, action: str = "has"
) -> tuple[uuid.UUID, str]:
    """Company Insight with an approved Services born from its root; returns the company id and
    the Services id."""
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    [created] = await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": str(company_id),
                "parentId": str(root_id),
                "label": "Services",
                "domainKey": "sales",
                "action": action,
            }
        ],
    )
    approved = await client.post(
        f"/proposals/{created['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200, approved.text
    return company_id, created["conceptId"]


def births(result: dict) -> list[tuple]:
    return [(d["type"], d.get("label"), d.get("parentId"), d["action"]) for d in result["drafts"]]


def split_into(services_id: str) -> list[tuple]:
    return [
        ("concept", "AI", services_id, "is split into"),
        ("concept", "Data", services_id, "is split into"),
        ("concept", "Apps", services_id, "is split into"),
    ]


async def test_spoken_the_split_is_born_from_the_existing_services_and_the_restatement_is_a_note(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, services_id = await with_approved_services(client, tenant)
    fake_llm.answer(recorded("speech_insight_has_services_split"))

    result = await speak(client, tenant, company_id, SENTENCE)

    sent = fake_llm.context()
    assert [(c["handle"], c["label"]) for c in sent["candidates"]] == [
        ("c0", "Insight"),
        ("c1", "Services"),
    ]
    assert (result["extractor"], result["llmOutcome"], result["outcome"]) == (
        "llm",
        "used",
        "understood",
    )
    assert births(result) == split_into(services_id)
    assert len(result["draftNotes"]) == 3
    assert result["unresolved"] == []
    assert result["statements"][0] == KNOWN
    assert result["intents"][0]["objectResolved"] == services_id
    assert result["caption"].startswith(KNOWN + " · Services is split into AI (new)")
    created = await submit(client, tenant, result["drafts"])
    assert [p["type"] for p in created] == ["concept"] * 3


async def test_typed_the_split_is_born_from_the_existing_services_and_the_restatement_is_a_note(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, services_id = await with_approved_services(client, tenant)
    fake_llm.answer(recorded("insight_has_services_split"))

    result = await teach(client, tenant, company_id, SENTENCE)

    assert (result["extractor"], result["llmOutcome"]) == ("llm", "used")
    assert births(result) == split_into(services_id)
    assert result["statements"][0] == KNOWN
    assert result["unresolved"] == []
    await submit(client, tenant, result["drafts"])


async def test_a_new_relation_between_existing_concepts_is_still_drafted(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, services_id = await with_approved_services(client, tenant, action="sells")
    fake_llm.answer(recorded("insight_has_services_split"))

    result = await teach(client, tenant, company_id, SENTENCE)

    assert births(result)[0] == ("relation", None, None, "has")
    assert births(result)[1:] == split_into(services_id)
    await submit(client, tenant, result["drafts"])


async def test_a_new_label_naming_the_existing_services_reuses_it(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, services_id = await with_approved_services(client, tenant)
    answer = json.loads(recorded("insight_has_services_split"))
    for intent in answer["intents"]:
        for end in ("subject", "object"):
            if intent[end] == {"candidate": "c1"}:
                intent[end] = {"newLabel": "Services"}
    fake_llm.answer(json.dumps(answer))

    result = await teach(client, tenant, company_id, SENTENCE)

    assert births(result) == split_into(services_id)
    assert result["statements"][0] == KNOWN


async def test_a_sentence_that_only_restates_the_model_drafts_nothing_and_waits_for_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await with_approved_services(client, tenant)
    answer = json.loads(recorded("insight_has_services_split"))
    answer["intents"] = answer["intents"][:1]
    fake_llm.answer(json.dumps(answer))

    result = await teach(client, tenant, company_id, "Insight has services, they matter.")

    assert result["drafts"] == [] and result["draftNotes"] == []
    assert result["outcome"] == "understood"
    assert result["caption"] == KNOWN + "."


async def test_a_concept_the_sentence_names_is_sent_even_when_session_turns_fill_the_list(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, _ = await with_approved_services(client, tenant)
    session_id = uuid.uuid4()
    # The grammar seeds the session with the step off.
    await configure(tenant, llm_monthly_token_cap=0)
    seeded = await teach(client, tenant, company_id, "A plant has machines", session_id)
    await submit(client, tenant, seeded["drafts"])
    await configure(tenant)
    monkeypatch.setattr(teach_extraction_service, "MAX_CANDIDATES", 2)
    fake_llm.answer(recorded("insight_has_services_split"))

    await teach(client, tenant, company_id, SENTENCE, session_id)

    assert [c["label"] for c in fake_llm.context()["candidates"]] == ["Insight", "Services"]
