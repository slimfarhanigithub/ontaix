"""Spoken sentences sent one at a time in one teach session: back-references to what earlier
sentences introduced, properties that are not concepts, and misheard names.

The regression case is the owner's own recording, one request per finished sentence, with each
parse's drafts proposed before the next sentence as the Studio does. Recorded answers only; no
test reaches a provider.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import speak, submit

pytestmark = pytest.mark.asyncio(loop_scope="session")

RECORDING = [
    "Insight sells financial services to its customers",
    "these services are split in advisory and um managed services",
    "the managed ones are billed monthly",
    "advisory is billed per day",
    "ADNOC buys them both",
    "its subsidiaries XRG and Drilling buy advisory",
]


def rel(sentence: str, subject: dict, action: str, obj: dict, span: str, **extra: object) -> dict:
    start = sentence.index(span)
    return {
        "kind": "rel",
        "subject": subject,
        "action": action,
        "object": obj,
        "confidence": 0.9,
        "span": span,
        "segment": 0,
        "source": {"start": start, "end": start + len(span)},
        **extra,
    }


def answer(sentence: str, intents: list[dict], unresolved: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "intents": intents,
            "unresolved": unresolved or [],
            "segments": [{"index": 0, "start": 0, "end": len(sentence)}],
        }
    )


def not_understood(sentence: str) -> dict:
    return {
        "text": sentence,
        "reason": "not_understood",
        "source": {"start": 0, "end": len(sentence)},
    }


def handle(context: dict, label: str) -> str:
    return next(c["handle"] for c in context["candidates"] if c["label"] == label)


def new(label: str) -> dict:
    return {"newLabel": label}


def cand(h: str) -> dict:
    return {"candidate": h}


async def test_the_owners_recording_drills_down_through_the_session(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    session_id = uuid.uuid4()
    s = RECORDING
    # The answers the live model gave with the session's pending concepts as candidates; the
    # handles are checked against what each request actually sent.
    fake_llm.answer(
        answer(
            s[0],
            [
                rel(
                    s[0],
                    cand("c0"),
                    "sells",
                    new("Financial services"),
                    "Insight sells financial services",
                ),
                rel(s[0], new("Financial services"), "is sold to", new("Customers"), s[0]),
            ],
        ),
        answer(
            s[1],
            [
                rel(
                    s[1],
                    cand("c1"),
                    "is split into",
                    new("Advisory"),
                    "these services are split in advisory",
                    listId=0,
                ),
                rel(
                    s[1],
                    cand("c1"),
                    "is split into",
                    new("Managed services"),
                    "managed services",
                    listId=0,
                ),
            ],
        ),
        answer(s[2], [], [not_understood(s[2])]),
        answer(s[3], [], [not_understood(s[3])]),
        answer(
            s[4],
            [
                rel(s[4], new("ADNOC"), "buys", cand("c2"), s[4]),
                rel(s[4], new("ADNOC"), "buys", cand("c3"), s[4]),
            ],
        ),
        answer(
            s[5],
            [
                rel(
                    s[5],
                    cand("c3"),
                    "has",
                    new("Subsidiaries"),
                    "its subsidiaries XRG and Drilling",
                    members=[new("XRG"), new("Drilling")],
                    memberAction="includes",
                ),
                rel(s[5], new("XRG"), "buys", cand("c1"), "XRG and Drilling buy advisory"),
                rel(s[5], new("Drilling"), "buys", cand("c1"), "Drilling buy advisory"),
            ],
        ),
    )

    results = []
    for sentence in RECORDING:
        result = await speak(client, tenant, company_id, sentence, session_id)
        assert (result["extractor"], result["llmOutcome"]) == ("llm", "used")
        if result["drafts"]:
            await submit(client, tenant, result["drafts"])
        results.append(result)

    contexts = [fake_llm.context(i) for i in range(len(RECORDING))]
    # Every sentence after the first sees the earlier sentences of the recording.
    for i, context in enumerate(contexts):
        assert [t["sentence"] for t in context["sessionTurns"]] == RECORDING[:i]
    # What earlier sentences introduced is pending, and a candidate before the sentence that
    # only points back at it.
    assert handle(contexts[1], "Financial services") == "c1"
    for i in (2, 4):
        assert handle(contexts[i], "Advisory") == "c2"
        assert handle(contexts[i], "Managed services") == "c3"
        pending = {c["label"]: c["pending"] for c in contexts[i]["candidates"]}
        assert pending["Advisory"] and pending["Managed services"]
    assert (handle(contexts[5], "ADNOC"), handle(contexts[5], "Advisory")) == ("c3", "c1")
    assert contexts[4]["sessionTurns"][1]["introduced"] == ["c2", "c3"]

    statements = [r["statements"] for r in results]
    assert statements[1] == [
        "Financial services is split into Advisory (new)",
        "Financial services is split into Managed services (new)",
    ]
    # Billing is a property: no concept for a unit or a frequency.
    for i in (2, 3):
        assert results[i]["drafts"] == []
        assert results[i]["unresolved"] == [{"text": s[i], "reason": "not_understood"}]
    assert statements[4] == ["ADNOC (new) buys Advisory", "ADNOC buys Managed services"]
    assert statements[5] == [
        "ADNOC has Subsidiaries (new)",
        "Subsidiaries includes XRG (new)",
        "Subsidiaries includes Drilling (new)",
        "XRG buys Advisory",
        "Drilling buys Advisory",
    ]
    labels = [d.get("label") for r in results for d in r["drafts"] if d["type"] == "concept"]
    assert "Day" not in labels and "Monthly billing" not in labels
    assert labels.count("Advisory") == 1 and labels.count("ADNOC") == 1


async def test_a_label_an_earlier_sentence_introduced_but_nobody_proposed_is_not_minted(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    session_id = uuid.uuid4()
    first, second = RECORDING[1], RECORDING[2]
    fake_llm.answer(
        answer(
            first, [rel(first, cand("c0"), "sells", new("Managed services"), "managed services")]
        ),
        answer(second, [rel(second, new("Managed services"), "is billed", new("Monthly"), second)]),
    )

    await speak(client, tenant, company_id, first, session_id)
    result = await speak(client, tenant, company_id, second, session_id)

    context = fake_llm.context(1)
    # The unproposed label is context, shown as a plain label, never a candidate.
    assert context["sessionTurns"][0]["introduced"] == ["Managed services"]
    assert "Managed services" not in [c["label"] for c in context["candidates"]]
    # Grounding reads the current sentence only, so the repeated label mints nothing.
    assert result["drafts"] == []
    assert result["unresolved"] == [{"text": second, "reason": "ungrounded_label"}]


async def test_a_spoken_name_that_sounds_like_an_existing_concept_is_listed_not_created(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Amdaris")
    await configure(tenant)
    heard = "ahmedabus sells services to its customers"
    fake_llm.answer(
        answer(
            heard,
            [
                rel(heard, new("Ahmedabus"), "sells", new("Services"), "ahmedabus sells services"),
                rel(heard, cand("c0"), "sells to", new("Customers"), heard),
            ],
        ),
        answer(
            heard,
            [rel(heard, new("Ahmedabus"), "sells", new("Services"), "ahmedabus sells services")],
        ),
    )

    spoken = await speak(client, tenant, company_id, heard)

    assert spoken["statements"] == ["Amdaris sells to Customers (new)"]
    assert {"text": "ahmedabus sells services", "reason": "ambiguous_reference"} in spoken[
        "unresolved"
    ]
    assert "Ahmedabus" not in [d.get("label") for d in spoken["drafts"]]

    # Typed text has no recognition errors: the same label is drafted.
    typed = await client.post(
        "/teach/parse",
        json={"companyId": str(company_id), "text": heard},
        headers=tenant.builder.headers,
    )
    assert typed.status_code == 200, typed.text
    assert "Ahmedabus" in [d.get("label") for d in typed.json()["drafts"]]


async def test_a_group_keeps_each_left_out_members_own_reason(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Amdaris")
    await configure(tenant)
    heard = "our teams are ahmedabus and Zorvik"
    fake_llm.answer(
        answer(
            heard,
            [
                rel(
                    heard,
                    cand("c0"),
                    "has",
                    new("Teams"),
                    heard,
                    members=[new("Ahmedabus"), new("Quillon"), new("Zorvik")],
                    memberAction="includes",
                ),
            ],
        )
    )

    spoken = await speak(client, tenant, company_id, heard)

    assert spoken["statements"] == ["Amdaris has Teams (new)", "Teams includes Zorvik (new)"]
    # One member sounds like Amdaris, another is not in the words: each reason is kept.
    assert spoken["unresolved"] == [
        {"text": heard, "reason": "ambiguous_reference"},
        {"text": heard, "reason": "ungrounded_label"},
    ]


async def test_a_label_starting_with_the_company_name_misheard_reuses_the_companys_concept(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    sales = {
        "type": "concept",
        "companyId": str(company_id),
        "parentId": str(root_id),
        "label": "Sales",
        "domainKey": "sales",
        "action": "has",
    }
    await submit(client, tenant, [sales])
    heard = "Inside sales come from software licenses or from services"
    fake_llm.answer(
        answer(
            heard,
            [
                rel(heard, cand("c0"), "has", new("Inside sales"), "Inside sales"),
                rel(
                    heard,
                    new("Inside sales"),
                    "comes from",
                    new("Software licenses"),
                    "Inside sales come from software licenses",
                ),
                rel(heard, new("Inside sales"), "comes from", new("Services"), heard),
            ],
        )
    )

    spoken = await speak(client, tenant, company_id, heard)

    labels = [d.get("label") for d in spoken["drafts"]]
    assert "Inside sales" not in labels
    assert spoken["statements"] == [
        "Insight has Sales (already in the model)",
        "Sales comes from Software licenses (new)",
        "Sales comes from Services (new)",
    ]
