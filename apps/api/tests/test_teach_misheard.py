"""Misheard terms, talk about the app and comma-less lists in speech: a corrected label is
grounded only through the words it was misheard as, in speech mode alone; the correction is
told to the reviewer; a fragment or an unclear phrase is listed, never drafted; app talk gives
nothing; every item of a list is drafted.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.services.teach_extraction_service import _sound_alike_run, examples_for
from app.utilities.sound_alike import sound_key, sound_like_word_together, sounds_like_word
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import speak, submit

# A recording as a recogniser hears it: a job title misheard in a list, a word heard as an
# article and a word, a fragment left behind, talk about the app.
ARCHITECTS = (
    "halvorn have engineers these engineers can be test engineers network engineers platform "
    "engineers also crowd architects they can have certifications either vendor certifications "
    "or cloud certifications"
)
KINDS = (
    "these engineers can be test engineers network engineers platform engineers also crowd "
    "architects"
)
DELIVERY = "cloud can have a jile delivery or a Delivery"
APP_TALK = "but it is still loading"


def spans(text: str, span: str) -> dict:
    start = text.index(span)
    return {"start": start, "end": start + len(span)}


def rel(text: str, subject: dict, obj: dict, action: str, span: str, **extra: object) -> dict:
    return {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.9,
        "span": span,
        "source": spans(text, span),
        "segment": 0,
        **extra,
    }


def spec(text: str, child: dict, parent: dict, span: str, **extra: object) -> dict:
    return {
        "kind": "spec",
        "subject": child,
        "object": parent,
        "confidence": 0.9,
        "span": span,
        "source": spans(text, span),
        "segment": 0,
        **extra,
    }


def answer(text: str, intents: list[dict], unresolved: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "intents": intents,
            "unresolved": unresolved or [],
            "segments": [{"index": 0, "start": 0, "end": len(text)}],
        }
    )


def new(label: str) -> dict:
    return {"newLabel": label}


C0 = {"candidate": "c0"}


@pytest.mark.parametrize(
    ("heard", "meant", "alike"),
    [
        ("crowd", "cloud", True),
        ("brand", "bland", True),
        ("insite", "insight", True),
        ("a", "AI", False),
        ("sales", "services", False),
        ("surfaces", "services", False),
        ("data", "apps", False),
        ("analysts", "cloud", False),
        ("machines", "backdoor", False),
        ("engineers", "engineers", False),
        ("engineer", "engineers", False),
        ("report", "reporting", False),
        ("reporting", "report", False),
        ("می‌خواهم", "خواهم", False),
    ],
)
def test_a_heard_word_sounds_like_the_word_meant(heard: str, meant: str, alike: bool) -> None:
    assert sounds_like_word(heard, meant) is alike


@pytest.mark.parametrize(
    ("first", "second", "meant", "alike"),
    [
        ("a", "jile", "agile", True),
        ("a", "nalytics", "analytics", True),
        ("an", "alytics", "analytics", True),
        ("farm", "assists", "pharmacists", False),
        ("also", "crowd", "cloud", False),
        ("a", "bcdef", "bcdef", False),
        ("a", "delivery", "managed", False),
        ("to", "have", "halvorn", False),
    ],
)
def test_two_heard_words_run_together_sound_like_one_word(
    first: str, second: str, meant: str, alike: bool
) -> None:
    assert sound_like_word_together(first, second, meant) is alike


def test_the_sound_key_spells_one_sound_one_way() -> None:
    assert sound_key("solution") == "solushen"
    assert sound_key("pharmacists") == sound_key("farmacists") == "farmasists"
    assert sound_key("insight") == sound_key("insite")


def test_a_corrected_label_is_grounded_only_through_words_that_sound_like_it() -> None:
    whole = (0, len(ARCHITECTS))
    assert _sound_alike_run("Cloud architects", ARCHITECTS, whole) == "crowd architects"
    # The run must lie inside the intent's range.
    assert _sound_alike_run("Cloud architects", ARCHITECTS, (0, 22)) is None
    # Every word must be the heard word or sound like it; a label that merely shares a word
    # with the words grounds nothing, and neither does one with no word in common.
    assert _sound_alike_run("Enterprise architects", ARCHITECTS, whole) is None
    assert _sound_alike_run("Backdoor", ARCHITECTS, whole) is None
    # Two heard words run together sound like one word of the term.
    assert _sound_alike_run("Agile delivery", DELIVERY, (0, len(DELIVERY))) == "a jile delivery"
    # A one-letter fragment tells nothing: "a Delivery" never grounds Managed delivery.
    assert _sound_alike_run("Managed delivery", DELIVERY, (0, len(DELIVERY))) is None
    # The words themselves are ordinary grounding, not a correction.
    assert _sound_alike_run("Crowd architects", ARCHITECTS, whole) is None


@pytest.mark.asyncio(loop_scope="session")
async def test_a_misheard_job_title_is_corrected_and_the_heard_words_are_told(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Halvorn")
    await configure(tenant)
    engineers = new("Engineers")
    fake_llm.answer(
        answer(
            ARCHITECTS,
            [
                rel(ARCHITECTS, C0, engineers, "has", "halvorn have engineers"),
                spec(ARCHITECTS, new("Test engineers"), engineers, KINDS),
                spec(ARCHITECTS, new("Network engineers"), engineers, KINDS),
                spec(ARCHITECTS, new("Platform engineers"), engineers, KINDS),
                spec(
                    ARCHITECTS,
                    new("Cloud architects"),
                    engineers,
                    KINDS,
                    explanation="heard 'crowd architects': a job title among job titles",
                ),
            ],
        )
    )

    result = await speak(client, tenant, company_id, ARCHITECTS, uuid.uuid4())

    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == ("llm", "used", False)
    labels = [d["label"] for d in result["drafts"]]
    # Every item of the comma-less list is drafted, the corrected one among them.
    assert labels == [
        "Engineers",
        "Test engineers",
        "Network engineers",
        "Platform engineers",
        "Cloud architects",
    ]
    assert "Crowd architects" not in labels
    assert result["unresolved"] == []
    assert "Cloud architects is a Engineers (heard 'crowd architects')" in result["statements"]
    assert "(heard 'crowd architects')" in result["caption"]
    note = result["draftNotes"][4]
    assert note["explanation"] == "heard 'crowd architects': a job title among job titles"
    # The explanation already states the heard words, so they are not repeated in it.
    assert note["explanation"].count("crowd architects") == 1
    created = await submit(client, tenant, result["drafts"])
    assert len(created) == 5


@pytest.mark.asyncio(loop_scope="session")
async def test_the_server_states_the_heard_words_when_the_model_does_not(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Halvorn")
    await configure(tenant)
    await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": str(company_id),
                "parentId": str(root_id),
                "label": "Cloud",
                "domainKey": "sales",
                "action": "has",
            }
        ],
    )

    def cite_cloud(data: dict) -> str:
        handle = next(c["handle"] for c in data["candidates"] if c["label"] == "Cloud")
        return answer(
            DELIVERY,
            [
                rel(
                    DELIVERY,
                    {"candidate": handle},
                    new("Agile delivery"),
                    "has",
                    "cloud can have a jile delivery",
                    explanation="a way of delivering beside the other",
                )
            ],
            [{"text": "a Delivery", "reason": "ambiguous_reference", "segment": 0}],
        )

    fake_llm.answer(cite_cloud)

    result = await speak(client, tenant, company_id, DELIVERY, uuid.uuid4())

    assert result["llmOutcome"] == "used"
    (draft,) = result["drafts"]
    assert draft["label"] == "Agile delivery"
    assert draft["caption"] == (
        "Agile delivery is kept. Cloud has Agile delivery. Heard 'a jile delivery'."
    )
    assert result["draftNotes"][0]["explanation"] == (
        "a way of delivering beside the other heard 'a jile delivery'"
    )
    assert result["statements"] == ["Cloud has Agile delivery (new) (heard 'a jile delivery')"]
    assert result["unresolved"] == [{"text": "a Delivery", "reason": "ambiguous_reference"}]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_correction_that_sounds_different_is_ungrounded_and_typed_text_corrects_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Halvorn")
    await configure(tenant)
    engineers = new("Engineers")
    kinds = [
        rel(ARCHITECTS, C0, engineers, "has", "halvorn have engineers"),
        spec(ARCHITECTS, new("Enterprise architects"), engineers, KINDS),
    ]
    corrected = [
        rel(ARCHITECTS, C0, engineers, "has", "halvorn have engineers"),
        spec(ARCHITECTS, new("Cloud architects"), engineers, KINDS),
    ]
    fake_llm.answer(answer(ARCHITECTS, kinds), answer(ARCHITECTS, corrected))

    spoken = await speak(client, tenant, company_id, ARCHITECTS, uuid.uuid4())
    # Typed text has no recognition errors: the same answer is not corrected.
    typed = await client.post(
        "/teach/parse",
        json={"companyId": str(company_id), "text": ARCHITECTS[:400]},
        headers=tenant.builder.headers,
    )

    assert [d["label"] for d in spoken["drafts"]] == ["Engineers"]
    assert spoken["unresolved"] == [{"text": KINDS, "reason": "ungrounded_label"}]
    assert typed.status_code == 200, typed.text
    assert [d["label"] for d in typed.json()["drafts"]] == ["Engineers"]
    assert typed.json()["unresolved"] == [{"text": KINDS, "reason": "ungrounded_label"}]


@pytest.mark.asyncio(loop_scope="session")
async def test_talk_about_the_app_drafts_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Halvorn")
    await configure(tenant)
    fake_llm.answer(
        answer(APP_TALK, [], [{"text": APP_TALK, "reason": "not_a_statement", "segment": 0}])
    )

    result = await speak(client, tenant, company_id, APP_TALK, uuid.uuid4())

    assert result["outcome"] == "not_understood"
    assert result["drafts"] == [] and result["intents"] == []
    assert result["unresolved"] == [{"text": APP_TALK, "reason": "not_a_statement"}]


def test_a_misheard_list_and_app_talk_retrieve_their_examples() -> None:
    chosen = examples_for(ARCHITECTS, "speech")
    assert any(e["input"]["sentence"] == ARCHITECTS for e in chosen)
    chosen = examples_for("as you can see it starts to draw them like this", "speech")
    assert any("as you can see it is processing" in e["input"]["sentence"] for e in chosen)
