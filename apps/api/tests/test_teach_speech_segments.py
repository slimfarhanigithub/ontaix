"""One spoken sentence per request: the model's segments of it overlap or go backwards.

The answers are rebuilt from the owner's live voice sentences, whose whole answers were refused
for their segments and left the grammar to draft word runs as labels. Recorded shapes only; no
test reaches a provider.
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure, teach
from tests.test_teach_grounding import new, speech_answer
from tests.test_teach_speech import births, speak

pytestmark = pytest.mark.asyncio(loop_scope="session")

SOFT_AND_OTHER = (
    "the employees have skills some of them are soft skills and the other ones are technical"
)
SOFT_AND_CALLED = (
    "employees have skills some of them are soft skills and some of them are called technical "
    "skills"
)


def _skills_answer(text: str, segments: list[tuple[int, int]], technical: str) -> str:
    """Employees has Skills in segment 0; Skills includes both kinds in segment 1."""

    def at(quote: str) -> dict:
        start = text.index(quote)
        return {"start": start, "end": start + len(quote)}

    return speech_answer(
        [
            {
                "subject": new("Employees"),
                "object": new("Skills"),
                "action": "has",
                "span": "employees have skills",
                "segment": 0,
                "source": at("employees have skills"),
            },
            {
                "subject": new("Skills"),
                "object": new("Soft skills"),
                "action": "includes",
                "span": "some of them are soft skills",
                "segment": 1,
                "source": at("some of them are soft skills"),
            },
            {
                "subject": new("Skills"),
                "object": new("Technical skills"),
                "action": "includes",
                "span": technical,
                "segment": 1,
                "source": at(technical),
            },
        ],
        segments,
    )


async def test_overlapping_segments_of_one_sentence_are_repaired_not_refused(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    # Segment 1 starts inside segment 0.
    fake_llm.answer(
        _skills_answer(
            SOFT_AND_CALLED, [(0, 34), (22, 95)], "some of them are called technical skills"
        )
    )

    result = await speak(client, tenant, company_id, SOFT_AND_CALLED)

    assert result["llmOutcome"] == "used"
    assert result["extractor"] == "llm"
    assert births(result) == [
        ("Employees", str(root_id), "has"),
        ("Skills", "Employees", "has"),
        ("Soft skills", "Skills", "includes"),
        ("Technical skills", "Skills", "includes"),
    ]
    assert result["unresolved"] == []
    assert result["segments"] == [{"index": 0, "span": {"start": 0, "end": len(SOFT_AND_CALLED)}}]
    assert {n["segment"] for n in result["draftNotes"]} == {0}


async def test_backward_segments_draft_no_word_run_labels(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    # Segment 1 goes back before the end of segment 0; "technical skills" is not in the text.
    fake_llm.answer(
        _skills_answer(SOFT_AND_OTHER, [(4, 54), (26, 87)], "the other ones are technical")
    )

    result = await speak(client, tenant, company_id, SOFT_AND_OTHER)

    assert result["llmOutcome"] == "used"
    labels = {d["label"] for d in result["drafts"]}
    assert labels == {"Employees", "Skills", "Soft skills"}
    assert result["unresolved"] == [
        {"text": "the other ones are technical", "reason": "ungrounded_label"}
    ]


async def test_overlapping_segments_of_a_long_transcript_are_merged_then_split_at_words(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    filler = "and we talk about the weather for a while before we get back to it " * 6
    transcript = f"{SOFT_AND_CALLED} {filler}then the plants have machines"
    assert len(transcript) > 400
    plants = transcript.index("the plants have machines")
    fake_llm.answer(
        speech_answer(
            [
                {
                    "subject": new("Employees"),
                    "object": new("Skills"),
                    "action": "has",
                    "span": "employees have skills",
                    "segment": 0,
                    "source": {"start": 0, "end": 21},
                },
                {
                    "subject": new("Plants"),
                    "object": new("Machines"),
                    "action": "has",
                    "span": "the plants have machines",
                    "segment": 1,
                    "source": {"start": plants, "end": len(transcript)},
                },
            ],
            # Segment 1 starts inside segment 0, and the two cover the whole transcript.
            [(0, 300), (200, len(transcript))],
        )
    )

    result = await speak(client, tenant, company_id, transcript)

    assert result["llmOutcome"] == "used"
    assert {d["label"] for d in result["drafts"]} == {"Employees", "Skills", "Plants", "Machines"}
    spans = [(s["span"]["start"], s["span"]["end"]) for s in result["segments"]]
    assert len(spans) == 2 and spans[0][0] == 0 and spans[1][1] == len(transcript)
    assert all(end - start <= 400 for start, end in spans) and spans[0][1] < spans[1][0]
    assert transcript[spans[0][1] - 1] != " " and transcript[spans[1][0]] != " "
    assert sorted({n["segment"] for n in result["draftNotes"]}) == [0, 1]


@pytest.mark.parametrize("origin", ["speech", "text"])
async def test_a_refused_answer_drafts_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient, origin: str
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    # An intent naming a segment the answer never gave is refused whatever the text's length.
    answer = json.loads(_skills_answer(SOFT_AND_OTHER, [(0, 87)], "the other ones are technical"))
    answer["intents"][1]["segment"] = 5
    fake_llm.answer(json.dumps(answer))

    if origin == "speech":
        result = await speak(client, tenant, company_id, SOFT_AND_OTHER)
    else:
        result = await teach(client, tenant, company_id, SOFT_AND_OTHER)

    assert result["llmOutcome"] == "invalid_output"
    assert result["outcome"] == "not_understood"
    assert result["drafts"] == [] and result["intents"] == []
    assert result["unresolved"] == [{"text": SOFT_AND_OTHER, "reason": "model_invalid_output"}]
