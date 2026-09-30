"""The timing breakdown of a parse: what the pipeline publishes and how the harness reports it.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import httpx
import pytest

from app.utilities.stage_clock import StageTimings, record_timings
from evals.aggregate import CaseUsage, stage_percentiles, summarise
from evals.candidate import RunConfig
from evals.case_runner import CaseResult
from evals.report import RunRecord, markdown
from evals.stages import ConfigRun, StageResult, _summarise
from evals.teach_case import TeachCase
from evals.workspace import UnitResult
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient, recorded
from tests.test_teach_extraction import FIRST, add_company, configure, teach

EXTRACTION_STAGES = [
    "budget",
    "candidates",
    "examples",
    "learning",
    "context",
    "reserve",
    "provider",
    "interpret",
    "settle",
    "total",
]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_parse_publishes_the_stages_of_the_request_and_of_the_model_step(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(recorded("insight_sells_services"))
    timings = record_timings()

    result = await teach(client, tenant, company_id, FIRST)

    assert result["llmOutcome"] == "used"
    assert [t.name for t in timings] == ["extraction", "parse"]
    extraction, parse = timings
    assert list(extraction.stages) == EXTRACTION_STAGES
    assert extraction.counts == {"input_tokens": 812, "output_tokens": 64}
    assert list(parse.stages) == [
        "view",
        "source",
        "grammar",
        "model",
        "drafts",
        "turns",
        "learning",
        "total",
    ]
    assert parse.stages["total"] >= parse.stages["model"] >= extraction.stages["provider"]


def test_stage_percentiles_are_per_clock_and_stage_over_the_parses_that_ran_it() -> None:
    timings = [
        StageTimings("parse", {"view": 10, "model": 2000, "total": 2100}),
        StageTimings("parse", {"view": 30, "model": 1000, "total": 1100}),
        StageTimings("parse", {"view": 20, "total": 40}),
        StageTimings("extraction", {"provider": 900}, {"output_tokens": 50}),
    ]

    percentiles = stage_percentiles(timings)

    assert list(percentiles) == ["parse", "extraction"]
    view = percentiles["parse"]["view"]
    assert (view.count, view.p50_ms, view.p90_ms, view.max_ms) == (3, 20, 30, 30)
    model = percentiles["parse"]["model"]
    assert (model.count, model.p50_ms, model.p90_ms, model.max_ms) == (2, 1000, 2000, 2000)
    tokens = percentiles["extraction"]["output_tokens"]
    assert (tokens.count, tokens.p50_ms) == (1, 50)


def test_the_report_gives_the_timing_breakdown_per_configuration() -> None:
    case = TeachCase(id="one", kind="text", company="Insight", input=["Insight sells services"])
    result = CaseResult("one", "text", "dataset", "typed", "m@none", 0)
    result.units = [UnitResult("Insight sells services", 200, 5)]
    result.timings = [
        StageTimings("extraction", {"provider": 1200, "total": 1300}, {"output_tokens": 64}),
        StageTimings("parse", {"view": 12, "model": 1300, "total": 1330}),
    ]
    result.usage = CaseUsage(units=1, timings=result.timings)
    stage = StageResult("screening", runs=[ConfigRun(RunConfig("m", "none", None), 0, [result])])
    _summarise(stage)
    record = RunRecord("now", True, 1.0, 0.0, {}, [case], [], [], [stage])

    report = markdown(record)

    assert "### Screening Timing Breakdown For m@none" in report
    assert "| extraction | provider | 1 | 1200 | 1200 | 1200 |" in report
    assert "| parse | model | 1 | 1300 | 1300 | 1300 |" in report
    summary = summarise("m@none", "all", [(None, result.usage)])
    assert summary.stage_timings["extraction"]["output_tokens"].p50_ms == 64
