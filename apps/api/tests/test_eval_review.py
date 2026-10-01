"""The bake-off's review pass: a deeper model's corrections, grounded, applied and scored apart."""

from __future__ import annotations

import json

import pytest

from app.clients.llm_client import LlmAnswer, LlmProviderError, LlmRequest
from evals.candidate import RunConfig
from evals.case_runner import CaseResult
from evals.recording_llm_client import Budget
from evals.report import RunRecord, markdown, review_rows
from evals.review_pass import Correction, Reviewer, apply_corrections
from evals.scoring import PredictedConcept, PredictedRelation, score_case
from evals.stages import ConfigRun, StageResult
from evals.workspace import UnitResult
from tests.test_eval_speech import RECORDING

SOURCE = "\n".join(RECORDING.input)
DRAFTED = [
    PredictedConcept("Depot", "Harlow Freight", "runs"),
    # Misheard: the recording says cold store.
    PredictedConcept("Cold star", "Depot", "has"),
    PredictedConcept("Chilled bays", "Cold star", "is split into"),
    # A verb read as a name.
    PredictedConcept("Split", "Cold star", "is"),
]


def test_corrections_are_grounded_and_applied_to_the_tree() -> None:
    corrections = [
        Correction(kind="rename", label="Cold star", to="Cold store", reason="misheard"),
        Correction(kind="delete", label="Split", reason="a verb read as a name"),
        Correction(
            kind="add",
            label="Frozen bays",
            parent="Cold store",
            action="is split into",
            reason="stated",
        ),
        # Refused: not the recording's words, an unknown concept, a parent that does not exist.
        Correction(kind="rename", label="Depot", to="Warehouse", reason="nicer"),
        Correction(kind="move", label="Loading dock", parent="Depot", reason="unknown"),
        Correction(
            kind="add", label="Cold store", parent="Nowhere", action="has", reason="unknown parent"
        ),
    ]

    applied = apply_corrections(
        corrections,
        RECORDING,
        DRAFTED,
        [PredictedRelation("Cold star", "Depot", "sits in")],
        SOURCE,
    )

    assert applied.applied == 3
    assert applied.refused == {"ungrounded_label": 1, "unknown_concept": 1, "unknown_parent": 1}
    assert [(c.label, c.parent) for c in applied.concepts] == [
        ("Depot", "Harlow Freight"),
        ("Cold store", "Depot"),
        ("Chilled bays", "Cold store"),
        ("Frozen bays", "Cold store"),
    ]
    assert applied.relations == [PredictedRelation("Cold store", "Depot", "sits in")]
    before = score_case(RECORDING, DRAFTED, [], SOURCE)
    after = score_case(RECORDING, applied.concepts, applied.relations, SOURCE)
    assert (before.parent_at_depth, after.parent_at_depth) == (1, 4)
    assert (len(before.invented), len(after.invented)) == (2, 0)


class _Answering:
    provider = model = "reviewer"

    def __init__(self, answer: str | LlmProviderError) -> None:
        self.answer = answer
        self.requests: list[LlmRequest] = []

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return 1

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        self.requests.append(request)
        if isinstance(self.answer, LlmProviderError):
            raise self.answer
        return LlmAnswer(self.answer, 3000, 120, 0.02, 4200)


@pytest.mark.asyncio(loop_scope="session")
async def test_the_reviewer_scores_before_and_after_and_charges_the_budget() -> None:
    answer = json.dumps(
        {
            "corrections": [
                {"kind": "rename", "label": "Cold star", "to": "cold store", "reason": "misheard"},
                {"kind": "delete", "label": "Split", "reason": "a verb"},
            ]
        }
    )
    client = _Answering(answer)
    budget = Budget(1.0)
    reviewer = Reviewer(client, budget)

    result = await reviewer.review(RECORDING, DRAFTED, [], [], SOURCE)

    assert (result.corrections, result.applied, result.refused) == (2, 2, {})
    assert result.before is not None and result.after is not None
    assert (result.before.parent_at_depth, result.after.parent_at_depth) == (1, 3)
    assert (result.cost_eur, result.latency_ms, result.error) == (0.02, 4200, None)
    assert budget.spent_eur == 0.02
    sent = json.loads(client.requests[0].user)
    assert sent["sentences"] == RECORDING.input and sent["company"] == "Harlow Freight"
    assert [c["label"] for c in sent["concepts"]] == ["Depot", "Cold star", "Chilled bays", "Split"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_failed_review_keeps_the_score_and_is_recorded() -> None:
    reviewer = Reviewer(_Answering(LlmProviderError("status", cost_eur=0.001)), Budget(1.0))

    result = await reviewer.review(RECORDING, DRAFTED, [], [], SOURCE)

    assert result.error == "LlmProviderError: status" and result.after is None
    assert result.before is not None and result.before.parent_at_depth == 1


def test_the_report_gives_the_review_pass_per_recording() -> None:
    result = CaseResult("recording", "speech", "dataset", "speech", "m@none", 0)
    result.units = [UnitResult(s, 200, 1) for s in RECORDING.input]
    result.score = score_case(RECORDING, DRAFTED, [], SOURCE)
    from evals.review_pass import ReviewResult

    result.review = ReviewResult(
        corrections=2,
        applied=2,
        before=result.score,
        after=score_case(RECORDING, DRAFTED[:1], [], SOURCE),
        cost_eur=0.03,
        latency_ms=5000,
    )
    stage = StageResult("screening", runs=[ConfigRun(RunConfig("m", "none", None), 0, [result])])
    record = RunRecord("now", True, 1.0, 0.0, {}, [RECORDING], [], [], [stage])

    (row,) = review_rows(stage)
    report = markdown(record)

    assert (row["parentAtDepthBefore"], row["parentAtDepthAfter"]) == (1, 1)
    assert (row["inventedBefore"], row["inventedAfter"]) == (2, 0)
    assert "### Screening Review Pass" in report
    assert "0.0100 EUR per reviewed sentence" in report
