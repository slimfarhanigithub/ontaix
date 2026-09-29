"""Answer shapes Claude and GPT gave on live transcripts that the API refused, rebuilt on made-up
text: a transcript answer without segments and segment offsets drifted into words. Recorded
answers only."""

from __future__ import annotations

import json

import httpx
import jsonschema
import pytest

from app.ai.prompts.teach_extraction import OUTPUT_SCHEMA, SPEECH_OUTPUT_SCHEMA, SYSTEM_PROMPT
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure, teach
from tests.test_teach_grounding import C0, new, speech_answer
from tests.test_teach_speech import births, speak


@pytest.mark.asyncio(loop_scope="session")
async def test_a_transcript_is_asked_for_segments_and_typed_text_is_not(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Acme")
    await configure(tenant)
    answer = json.dumps({"intents": [], "unresolved": []})
    fake_llm.answer(answer, answer)

    await speak(client, tenant, company_id, "acme builds bikes")
    await teach(client, tenant, company_id, "Acme builds bikes and frames and wheels")

    spoken, typed = (r.output_schema for r in fake_llm.requests)
    assert spoken is SPEECH_OUTPUT_SCHEMA and typed is OUTPUT_SCHEMA
    assert "segments" in spoken["required"]
    assert "segment" in spoken["properties"]["intents"]["items"]["required"]
    assert "segment" not in typed["properties"]["intents"]["items"]["required"]


def test_the_speech_format_refuses_a_transcript_answer_without_segments() -> None:
    # A live Claude answer to a transcript: the loose format let it leave out every segment.
    unsegmented = {
        "intents": [
            {
                "kind": "rel",
                "subject": {"newLabel": "Bikes"},
                "object": {"candidate": "c1"},
                "action": "sells to",
                "confidence": 0.85,
                "span": "bikes go to retailers",
                "source": {"start": 7, "end": 28},
                "listId": 0,
            }
        ],
        "unresolved": [],
    }
    jsonschema.Draft202012Validator(OUTPUT_SCHEMA).validate(unsegmented)
    assert not jsonschema.Draft202012Validator(SPEECH_OUTPUT_SCHEMA).is_valid(unsegmented)
    without_intent_segment = {**unsegmented, "segments": [{"index": 0, "start": 0, "end": 28}]}
    assert not jsonschema.Draft202012Validator(SPEECH_OUTPUT_SCHEMA).is_valid(
        without_intent_segment
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_segment_offsets_drifted_into_words_move_to_the_nearer_edge(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Acme")
    await configure(tenant)
    transcript = "okay um acme has four plants they are organised in regions like north and south"
    # Every offset is two code points late: segment 0 ends inside "they" and segment 1 starts
    # inside it, so moving both boundaries out made the segments overlap.
    fake_llm.answer(
        speech_answer(
            [
                {
                    "subject": C0,
                    "object": new("Plants"),
                    "action": "has",
                    "span": "acme has four plants",
                    "segment": 0,
                    "source": {"start": 10, "end": 30},
                },
                {
                    "subject": new("Plants"),
                    "object": new("Regions"),
                    "action": "has",
                    "span": "they are organised in regions",
                    "segment": 1,
                    "source": {"start": 31, "end": 60},
                },
            ],
            [(10, 30), (31, 81)],
        )
    )

    result = await speak(client, tenant, company_id, transcript)

    assert result["llmOutcome"] == "used"
    assert births(result) == [("Plants", str(root_id), "has"), ("Regions", "Plants", "has")]
    assert result["segments"] == [
        {"index": 0, "span": {"start": 8, "end": 28}},
        {"index": 1, "span": {"start": 29, "end": 79}},
    ]


def test_the_instructions_state_the_rules_the_api_checks() -> None:
    # Each rule below refused whole live answers while the instructions left it unsaid.
    assert "source and span lie inside that one segment" in SYSTEM_PROMPT
    assert "explanation is at most 120 characters" in SYSTEM_PROMPT
    assert "from 0 to 1000, and only with members or a listId" in SYSTEM_PROMPT
    assert "memberAction comes only with members" in SYSTEM_PROMPT
    assert "Candidates with a company field belong to another company" in SYSTEM_PROMPT
