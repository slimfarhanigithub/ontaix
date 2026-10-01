"""A multi-word label spoken in the singular and in the plural names one concept.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.services.teach_extraction_service import _matches, _phrases
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import births, speak, submit

FIRST = (
    "okay so the sensor network ontology um is about systems observations and features of interest"
)
SECOND = "each observation has a result and it's about a feature of interest"


def rel(subject: dict, obj: dict, action: str, span: str, text: str) -> dict:
    start = text.index(span)
    return {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.9,
        "span": span,
        "segment": 0,
        "source": {"start": start, "end": start + len(span)},
    }


def answer(text: str, *intents: dict) -> str:
    return json.dumps(
        {
            "segments": [{"index": 0, "start": 0, "end": len(text)}],
            "intents": list(intents),
            "unresolved": [],
        }
    )


C0 = {"candidate": "c0"}


def new(label: str) -> dict:
    return {"newLabel": label}


@pytest.mark.asyncio(loop_scope="session")
async def test_a_later_singular_cites_the_plural_concept_instead_of_a_second_one(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Sensor Network Ontology")
    await configure(tenant)
    session_id = uuid.uuid4()
    fake_llm.answer(
        answer(
            FIRST,
            rel(C0, new("Observations"), "is about", "observations", FIRST),
            rel(C0, new("Features of interest"), "is about", "features of interest", FIRST),
        ),
        answer(
            SECOND,
            rel(new("Observation"), new("Result"), "has", "each observation has a result", SECOND),
            rel(
                new("Observation"),
                new("Feature of interest"),
                "is about",
                "it's about a feature of interest",
                SECOND,
            ),
        ),
    )
    first = await speak(client, tenant, company_id, FIRST, session_id)
    observations, _ = await submit(client, tenant, first["drafts"])

    second = await speak(client, tenant, company_id, SECOND, session_id)

    assert births(first) == [
        ("Observations", str(root_id), "is about"),
        ("Features of interest", str(root_id), "is about"),
    ]
    assert second["unresolved"] == []
    concepts = [d for d in second["drafts"] if d["type"] == "concept"]
    relations = [d for d in second["drafts"] if d["type"] == "relation"]
    assert [(d["label"], d.get("parentId")) for d in concepts] == [
        ("Result", observations["conceptId"])
    ]
    assert len(relations) == 1
    assert relations[0]["action"] == "is about"
    assert "Features of interest" in " ".join(second["statements"])


@pytest.mark.asyncio(loop_scope="session")
async def test_singular_and_plural_of_one_label_in_one_answer_are_one_new_concept(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "ValueFlows")
    await configure(tenant)
    text = "economic events are recorded and each economic event has an agent"
    fake_llm.answer(
        answer(
            text,
            rel(C0, new("Economic events"), "records", "economic events are recorded", text),
            rel(
                new("Economic event"), new("Agent"), "has", "each economic event has an agent", text
            ),
        )
    )

    result = await speak(client, tenant, company_id, text)

    assert result["unresolved"] == []
    assert births(result) == [
        ("Economic events", str(root_id), "records"),
        ("Agent", "Economic events", "has"),
    ]


def test_a_candidate_matches_the_sentence_whatever_the_number_of_any_of_its_words() -> None:
    phrases = _phrases(SECOND)

    assert _matches("Features of interest", phrases)
    assert _matches("Feature Of Interest", phrases)
    assert _matches("Observations", phrases)
    assert not _matches("Interest rates", phrases)
