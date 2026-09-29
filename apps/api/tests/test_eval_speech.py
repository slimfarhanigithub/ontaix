"""The bake-off's speech mode, its comprehension metrics and the private-case residency rule."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from evals.candidate import RunConfig
from evals.case_runner import CaseResult
from evals.input_modes import DocumentCache, SpeechMode
from evals.report import RunRecord, markdown, speech_rows
from evals.scoring import PredictedConcept, score_case
from evals.stages import ConfigRun, StageResult
from evals.teach_bakeoff import _eligibility
from evals.teach_case import MAX_SPOKEN_SENTENCE_CHARS, TeachCase
from evals.workspace import UnitResult, Workspace

RECORDING = TeachCase.model_validate(
    {
        "id": "recording",
        "kind": "speech",
        "company": "Harlow Freight",
        "input": [
            "so um Harlow Freight runs a depot",
            "and uh the depot has a cold store",
            "the cold store is split into chilled bays and frozen bays",
        ],
        "expected": {
            "concepts": [
                {"label": "Depot", "parent": "Harlow Freight", "action": "runs"},
                {"label": "Cold store", "parent": "Depot", "action": "has"},
                {"label": "Chilled bays", "parent": "Cold store", "action": "is split into"},
                {"label": "Frozen bays", "parent": "Cold store", "action": "is split into"},
            ]
        },
    }
)


async def test_a_recording_is_sent_sentence_by_sentence_as_speech_in_one_session() -> None:
    sent: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"drafts": [], "extractor": "llm", "llmOutcome": "ok"})

    transport = httpx.MockTransport(answer)
    async with httpx.AsyncClient(transport=transport, base_url="http://eval") as client:
        ws = Workspace(client, RECORDING)
        ws.company_id = uuid.uuid4()
        output = await SpeechMode().run(ws, RECORDING, DocumentCache())

    assert [body["text"] for body in sent] == RECORDING.input
    assert {body["origin"] for body in sent} == {"speech"}
    assert len({body["sessionId"] for body in sent}) == 1
    assert len(output.units) == 3


def test_a_speech_case_holds_one_input_per_finished_sentence() -> None:
    assert RECORDING.input[1] == "and uh the depot has a cold store"
    with pytest.raises(ValueError, match="spoken sentence"):
        TeachCase.model_validate(
            {
                "id": "long",
                "kind": "speech",
                "company": "X",
                "input": ["short", "a" * (MAX_SPOKEN_SENTENCE_CHARS + 1)],
            }
        )


def test_parent_at_depth_needs_the_right_parent_at_the_expected_level() -> None:
    drafts = [
        PredictedConcept("Depot", "Harlow Freight", "runs"),
        # Right parent, but the cold store sits one level too deep under an invented yard.
        PredictedConcept("Yard", "Depot", "has"),
        PredictedConcept("Cold store", "Yard", "has"),
        PredictedConcept("Chilled bays", "Cold store", "is split into"),
        PredictedConcept("Frozen bays", "Harlow Freight", "has"),
    ]

    score = score_case(RECORDING, drafts, [], " ".join(RECORDING.input))

    assert score.parent_correct == 2
    assert score.parent_at_depth == 1
    assert score.wrong_depth == ["Chilled bays: level 4, want 3"]
    assert score.invented == ["Yard"]
    assert score.missed == []
    assert (score.depth_achieved, score.depth_expected) == (4, 3)


def test_the_report_gives_speech_comprehension_per_case() -> None:
    drafts = [
        PredictedConcept("Depot", "Harlow Freight", "runs"),
        PredictedConcept("Cold store", "Depot", "has"),
        PredictedConcept("Chilled bays", "Cold store", "includes"),
        PredictedConcept("Loading bay", "Depot", "has"),
    ]
    result = CaseResult("recording", "speech", "dataset", "speech", "m@none", 1)
    result.units = [UnitResult(s, 200, 1) for s in RECORDING.input]
    result.score = score_case(RECORDING, drafts, [], " ".join(RECORDING.input))
    config = RunConfig("m", "none", None)
    stage = StageResult("screening", runs=[ConfigRun(config, 1, [result])])

    (row,) = speech_rows(stage)

    assert row["sentences"] == 3
    assert (row["parentAtDepth"], row["expected"]) == (3, 4)
    assert (row["verbCorrect"], row["verbAccuracy"]) == (3, 1.0)
    assert row["relationAccuracy"] is None
    assert (row["depthReached"], row["depthGold"]) == (3, 3)
    assert row["invented"] == ["Loading bay"]
    assert row["missed"] == ["Frozen bays"]


def test_private_cases_reach_only_eu_data_zone_models_unless_allowed() -> None:
    private = RECORDING.model_copy(update={"origin": "private"})
    eu = RunConfig("gpt-6-sol", "none", None, "azure_foundry", "eu_data_zone")
    global_ = RunConfig("claude-sonnet-5", "none", None, "anthropic_foundry", "global")

    assert _eligibility(False)(eu, private)
    assert not _eligibility(False)(global_, private)
    assert _eligibility(False)(global_, RECORDING)
    assert _eligibility(True)(global_, private)


def test_the_markdown_report_lists_speech_rows() -> None:
    result = CaseResult("recording", "speech", "dataset", "speech", "m@none", 1)
    result.units = [UnitResult(s, 200, 1) for s in RECORDING.input]
    result.score = score_case(RECORDING, [], [], " ".join(RECORDING.input))
    stage = StageResult("screening", runs=[ConfigRun(RunConfig("m", "none", None), 1, [result])])
    record = RunRecord("now", True, 1.0, 0.0, {}, [RECORDING], [], [], [stage])

    assert "### Screening Speech Comprehension" in markdown(record)
