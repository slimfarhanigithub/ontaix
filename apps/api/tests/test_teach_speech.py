"""Speech goes to the language model first; grouping nouns, label casing and stated counts.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.llm_fakes import INPUT_TOKENS, OUTPUT_TOKENS, FakeLlmClient, recorded
from tests.test_teach_extraction import add_company, configure, rows, teach

pytestmark = pytest.mark.asyncio(loop_scope="session")

TRANSCRIPT = (
    "so, uh, Insight sells services. "
    "These services are focused around three areas, app, data and AI."
)


async def speak(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    company_id: uuid.UUID,
    transcript: str,
    session_id: uuid.UUID | None = None,
) -> dict:
    body: dict = {"companyId": str(company_id), "text": transcript, "origin": "speech"}
    if session_id is not None:
        body["sessionId"] = str(session_id)
    response = await client.post("/teach/parse", json=body, headers=tenant.builder.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def submit(client: httpx.AsyncClient, tenant: TenantFixture, drafts: list) -> list[dict]:
    created = await client.post(
        "/proposals/batch", json={"drafts": drafts}, headers=tenant.builder.headers
    )
    assert created.status_code == 202, created.text
    return created.json()


async def with_services(client: httpx.AsyncClient, tenant: TenantFixture) -> uuid.UUID:
    """Company Insight with a pending Services concept; returns the company id."""
    company_id, root_id = await add_company(tenant, "Insight")
    await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": str(company_id),
                "parentId": str(root_id),
                "label": "Services",
                "domainKey": "sales",
                "action": "sells",
            }
        ],
    )
    return company_id


def one_segment(name: str, transcript: str) -> str:
    """A recorded sentence answer as a transcript answer: one segment covering the transcript."""
    answer = json.loads(recorded(name))
    answer["segments"] = [{"index": 0, "start": 0, "end": len(transcript)}]
    for intent in answer["intents"]:
        intent["segment"] = 0
        intent["source"] = {"start": 0, "end": len(transcript)}
    return json.dumps(answer)


def births(result: dict) -> list[tuple]:
    return [
        (d["label"], d.get("parentId") or d.get("parentLabel"), d["action"])
        for d in result["drafts"]
    ]


async def test_a_spoken_transcript_goes_to_the_model_first_and_gives_four_concepts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    session_id = uuid.uuid4()
    fake_llm.answer(recorded("speech_insight_transcript"))

    result = await speak(client, tenant, company_id, TRANSCRIPT, session_id)

    sent = fake_llm.context()
    assert sent["mode"] == "speech" and sent["sentence"] == TRANSCRIPT
    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == ("llm", "used", False)
    assert result["origin"] == "speech"
    assert result["segments"] == [
        {"index": 0, "span": {"start": 8, "end": 31}},
        {"index": 1, "span": {"start": 32, "end": 96}},
    ]
    assert [n["segment"] for n in result["draftNotes"]] == [0, 1, 1, 1]
    assert result["draftNotes"][1]["sourceSpan"] == {"start": 32, "end": 96}
    assert births(result) == [
        ("Services", str(root_id), "sells"),
        ("App", "Services", "focuses on"),
        ("Data", "Services", "focuses on"),
        ("AI", "Services", "focuses on"),
    ]
    assert all(d["origin"] == "speech" for d in result["drafts"])
    assert [n["extractor"] for n in result["draftNotes"]] == ["llm"] * 4
    created = await submit(client, tenant, result["drafts"])
    assert len(created) == 4

    turns = await rows(
        "SELECT turn_index, sentence, new_labels FROM ontaix.teach_session_turn"
        " WHERE session_id = :s ORDER BY turn_index",
        s=session_id,
    )
    assert [(t["sentence"], t["new_labels"]) for t in turns] == [
        ("Insight sells services.", ["Services"]),
        (
            "These services are focused around three areas, app, data and AI.",
            ["App", "Data", "AI"],
        ),
    ]


async def test_the_same_content_spoken_in_two_requests_gives_the_same_concepts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    session_id = uuid.uuid4()
    said_first = "so, uh, Insight sells services."
    said_second = "These services are focused around three areas, app, data and AI."
    fake_llm.answer(
        one_segment("insight_sells_services", said_first),
        one_segment("insight_three_areas", said_second),
    )

    first = await speak(client, tenant, company_id, said_first, session_id)
    [services] = await submit(client, tenant, first["drafts"])
    second = await speak(client, tenant, company_id, said_second, session_id)

    assert fake_llm.context(1)["sessionTurns"][0]["introduced"] == ["c1"]
    assert births(first) + births(second) == [
        ("Services", str(root_id), "sells"),
        ("App", services["conceptId"], "focuses on"),
        ("Data", services["conceptId"], "focuses on"),
        ("AI", services["conceptId"], "focuses on"),
    ]
    assert (second["extractor"], second["llmOutcome"]) == ("llm", "used")


async def test_speech_with_the_model_off_falls_back_to_the_grammar(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant, llm_monthly_token_cap=0)

    result = await speak(client, tenant, company_id, TRANSCRIPT)

    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == (
        "rules",
        "budget_exhausted",
        True,
    )
    assert result["unresolved"] == [
        {"text": "so, uh, Insight sells services.", "reason": "model_unavailable"},
        {
            "text": "These services are focused around three areas, app, data and AI.",
            "reason": "model_unavailable",
        },
    ]
    assert [s["span"] for s in result["segments"]] == [
        {"start": 0, "end": 31},
        {"start": 32, "end": 96},
    ]
    assert all(n["extractor"] == "rules" for n in result["draftNotes"])
    assert fake_llm.requests == []


async def test_typed_speech_limits_stay_apart(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    long = "A plant has machines. " * 30
    typed = await client.post(
        "/teach/parse",
        json={"companyId": str(tenant.company_id), "text": long},
        headers=tenant.builder.headers,
    )
    spoken = await client.post(
        "/teach/parse",
        json={"companyId": str(tenant.company_id), "text": long, "origin": "speech"},
        headers=tenant.builder.headers,
    )
    assert typed.status_code == 422
    assert spoken.status_code == 200, spoken.text


async def test_a_grouping_noun_object_becomes_a_concept_and_labels_keep_their_casing(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await with_services(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded("services_offerings"))

    result = await teach(client, tenant, company_id, "Services has 3 offerings, APPS, Data and AI")

    services = next(c for c in fake_llm.context()["candidates"] if c["label"] == "Services")
    assert services["handle"] == "c1"
    assert (result["extractor"], result["llmOutcome"]) == ("llm", "used")
    offerings = result["drafts"][0]
    assert (offerings["label"], offerings["action"]) == ("Offerings", "has")
    # The label rule capitalises the first character and keeps the rest: APPS stays APPS.
    assert births(result)[1:] == [
        ("APPS", "Offerings", "includes"),
        ("Data", "Offerings", "includes"),
        ("AI", "Offerings", "includes"),
    ]
    assert result["outcome"] == "understood"
    await submit(client, tenant, result["drafts"])


async def test_the_same_sentence_spoken_gives_the_same_grouping(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await with_services(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded("speech_services_offerings"))

    result = await speak(client, tenant, company_id, "Services has 3 offerings, APPS, Data and AI.")

    assert fake_llm.context()["mode"] == "speech"
    assert [(label, action) for label, _, action in births(result)] == [
        ("Offerings", "has"),
        ("APPS", "includes"),
        ("Data", "includes"),
        ("AI", "includes"),
    ]


async def test_when_the_count_and_the_list_disagree_the_list_wins_with_a_note(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await with_services(client, tenant)
    await configure(tenant)
    fake_llm.answer(recorded("services_offerings_count_mismatch"))

    result = await teach(client, tenant, company_id, "Services has 2 offerings, APPS, Data and AI")

    assert [d["label"] for d in result["drafts"]] == ["Offerings", "APPS", "Data", "AI"]
    assert [n.get("explanation") for n in result["draftNotes"]] == ["stated 2, listed 3"] * 4


async def test_a_transcript_gets_the_speech_timeout_output_bound_and_parse_units(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(recorded("speech_insight_transcript"))

    await speak(client, tenant, company_id, TRANSCRIPT)

    request = fake_llm.requests[0]
    assert (request.timeout_seconds, request.max_output_tokens) == (45, 12288)
    [usage] = await rows(
        "SELECT tokens FROM ontaix.llm_month_usage WHERE tenant_id = :t", t=tenant.tenant_id
    )
    assert usage["tokens"] == INPUT_TOKENS + OUTPUT_TOKENS
    long = "A plant has machines. " * 40
    await speak(client, tenant, tenant.company_id, long[:810])
    [parse] = await rows(
        "SELECT spent FROM ontaix.rate_budget_window WHERE tenant_id = :t AND budget = 'parse'",
        t=tenant.tenant_id,
    )
    assert parse["spent"] == 1 + 3


async def test_a_document_sentence_goes_to_the_model_first_with_two_neighbours_each_side(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    await configure(tenant)
    lines = [
        "A carrier has trucks.",
        "A truck has pallets.",
        "A plant has machines.",
        "A machine has sensors.",
        "A sensor has readings.",
        "A reading has values.",
    ]
    upload = await client.post(
        "/import/sentences",
        files={"file": ("plant.txt", " ".join(lines).encode(), "text/plain")},
        headers=tenant.builder.headers,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["sentences"] == lines
    fake_llm.answer(
        json.dumps(
            {
                "intents": [
                    {
                        "kind": "rel",
                        "subject": {"newLabel": "Plant"},
                        "object": {"newLabel": "Machine"},
                        "action": "has",
                        "confidence": 0.9,
                        "source": {"start": 0, "end": len(lines[2])},
                    }
                ],
                "unresolved": [],
            }
        )
    )

    result = await teach(
        client,
        tenant,
        tenant.company_id,
        import_ref={"importId": upload.json()["importId"], "sentenceIndex": 2},
    )

    sent = fake_llm.context()
    assert sent["mode"] == "document" and sent["sentence"] == lines[2]
    assert sent["neighbours"] == {"before": lines[:2], "after": lines[3:5]}
    assert fake_llm.requests[0].timeout_seconds == 15
    assert (result["extractor"], result["llmOutcome"]) == ("llm", "used")
    # Labels are the caller's own words, sliced from the sentence: "machines" becomes Machines.
    assert [d["label"] for d in result["drafts"]] == ["Plant", "Machines"]
    assert all("importRef" in d for d in result["drafts"])
