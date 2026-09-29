"""The bake-off's two stages over the discovered cases.

Screening runs every configuration once on a stratified subset (about 30 % of each stratum of
origin, kind and first tag, at least one case per stratum, chosen by a stable hash so every
configuration sees the same cases). Finals run the best configurations by composite score, plus
the baseline, on every case with repeats; each repeat is summarised on its own, so the report
can give mean and standard deviation, and each case's mean over the repeats is compared with
the baseline's.

Cases of one configuration run concurrently, each in its own tenant; configurations run one
after the other, because the process holds one model client at a time. When the budget is
spent, no further case starts, the cases in flight finish, and the stage reports it stopped.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from evals.aggregate import RunSummary, summarise
from evals.candidate import RunConfig
from evals.case_runner import CaseResult, run_case
from evals.composite import Composite, Paired, composites, mean_std, paired
from evals.input_modes import DocumentCache, modes_for
from evals.recording_llm_client import BUDGET_REASON, Budget
from evals.teach_case import TeachCase

logger = logging.getLogger(__name__)

SCREENING_SHARE = 0.3
ALL_SUITES = "all"


@dataclass
class ConfigRun:
    config: RunConfig
    repeat: int
    results: list[CaseResult]
    capabilities: dict[str, object] = field(default_factory=dict)
    stopped_by_budget: bool = False
    # Cases this configuration may not receive (data residency).
    withheld: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    name: str
    runs: list[ConfigRun] = field(default_factory=list)
    summaries: dict[str, dict[str, RunSummary]] = field(default_factory=dict)
    composites: dict[str, Composite] = field(default_factory=dict)
    # Finals only: per configuration, the composite of each repeat and their mean and std.
    repeat_totals: dict[str, list[float]] = field(default_factory=dict)
    spread: dict[str, tuple[float, float]] = field(default_factory=dict)
    paired: list[Paired] = field(default_factory=list)
    stopped_by_budget: bool = False


# Installs a configuration's model client and returns its capabilities probe.
ClientInstaller = Callable[[RunConfig], Callable[[], dict[str, object]]]
# Whether a configuration may receive a case (the data residency rule).
Eligibility = Callable[[RunConfig, TeachCase], bool]
RESIDENCY_SKIP = "residency: private cases run only on EU data zone models"


def stratified_subset(cases: list[TeachCase], share: float, seed: str) -> list[TeachCase]:
    strata: dict[tuple[str, str, str], list[TeachCase]] = {}
    for c in cases:
        strata.setdefault((c.origin, c.kind, c.tags[0] if c.tags else ""), []).append(c)
    chosen: set[str] = set()
    for members in strata.values():
        ranked = sorted(members, key=lambda c: hashlib.sha256(f"{seed}:{c.id}".encode()).digest())
        chosen.update(c.id for c in ranked[: max(1, math.ceil(share * len(members)))])
    return [c for c in cases if c.id in chosen]


async def run_stage(
    name: str,
    configs: list[RunConfig],
    cases: list[TeachCase],
    document_modes: list[str],
    repeats: int,
    client: httpx.AsyncClient,
    docs: DocumentCache,
    install: ClientInstaller,
    budget: Budget,
    concurrency: int,
    eligible: Eligibility,
) -> StageResult:
    stage = StageResult(name)
    for config in configs:
        for repeat in range(repeats):
            if budget.exhausted:
                stage.stopped_by_budget = True
                break
            probe = install(config)
            allowed = [c for c in cases if eligible(config, c)]
            run = await _run_config(
                config, repeat, allowed, document_modes, client, docs, budget, concurrency
            )
            run.withheld = [c.id for c in cases if not eligible(config, c)]
            run.capabilities = probe()
            stage.runs.append(run)
            stage.stopped_by_budget |= run.stopped_by_budget
            logger.info(
                "%s %s repeat %d: %d cases, %.4f EUR spent so far",
                name,
                config.key,
                repeat + 1,
                len(run.results),
                budget.spent_eur,
            )
    _summarise(stage)
    return stage


def merge(name: str, stages: list[StageResult]) -> StageResult:
    """One stage holding the runs of several passes, summarised and ranked together."""
    merged = StageResult(name)
    for stage in stages:
        merged.runs.extend(stage.runs)
        merged.stopped_by_budget |= stage.stopped_by_budget
    _summarise(merged)
    return merged


def best_per_family(stage: StageResult, count: int) -> dict[str, list[str]]:
    """The deployments of the `count` best configurations of each family, by composite."""
    family = {r.config.key: (r.config.family, r.config.deployment) for r in stage.runs}
    out: dict[str, list[str]] = {}
    for comp in sorted(stage.composites.values(), key=lambda c: -c.total):
        fam, deployment = family[comp.run_key]
        chosen = out.setdefault(fam, [])
        if len(chosen) < count and deployment not in chosen:
            chosen.append(deployment)
    return out


def finalists(screening: StageResult, count: int, baseline: RunConfig) -> list[RunConfig]:
    """The `count` best configurations by composite, then the baseline if it is not one."""
    by_key = {r.config.key: r.config for r in screening.runs}
    ranked = sorted(screening.composites.values(), key=lambda c: -c.total)
    chosen = [by_key[c.run_key] for c in ranked[:count]]
    if baseline.key not in {c.key for c in chosen}:
        chosen.append(baseline)
    return chosen


def compare_with_baseline(stage: StageResult, baseline: RunConfig) -> None:
    """Each configuration's case-level F1 (groundable) against the baseline's, paired by case."""
    per_config: dict[str, dict[str, list[float]]] = {}
    for run in stage.runs:
        cases = per_config.setdefault(run.config.key, {})
        for r in run.results:
            if r.score is not None:
                key = f"{r.case_id}:{r.mode}"
                cases.setdefault(key, []).append(r.score.concept_f1_groundable)
    means = {k: {c: sum(v) / len(v) for c, v in cases.items()} for k, cases in per_config.items()}
    theirs = means.get(baseline.key)
    if theirs is None:
        return
    stage.paired = [
        paired(key, baseline.key, ours, theirs)
        for key, ours in means.items()
        if key != baseline.key
    ]


async def _run_config(
    config: RunConfig,
    repeat: int,
    cases: list[TeachCase],
    document_modes: list[str],
    client: httpx.AsyncClient,
    docs: DocumentCache,
    budget: Budget,
    concurrency: int,
) -> ConfigRun:
    run = ConfigRun(config, repeat, [])
    gate = asyncio.Semaphore(concurrency)
    jobs = [(case, mode) for case in cases for mode in modes_for(case, document_modes)]

    async def one(case: TeachCase, mode) -> CaseResult | None:
        async with gate:
            if budget.exhausted:
                run.stopped_by_budget = True
                return None
            result = await run_case(client, case, mode, docs, config.key, repeat)
            if any(c.error == BUDGET_REASON for c in result.calls):
                run.stopped_by_budget = True
                result.skipped = "budget spent during the case"
                result.score = None
            return result

    done = await asyncio.gather(*(one(case, mode) for case, mode in jobs))
    run.results = [r for r in done if r is not None]
    return run


def _summarise(stage: StageResult) -> None:
    by_repeat: dict[int, list[RunSummary]] = {}
    for run in stage.runs:
        usable = [r for r in run.results if not r.skipped]
        per_suite: dict[str, list[CaseResult]] = {}
        for r in usable:
            per_suite.setdefault(r.suite, []).append(r)
        suites = {
            suite: summarise(run.config.key, suite, [(r.score, r.usage) for r in rs])
            for suite, rs in sorted(per_suite.items())
        }
        overall = summarise(run.config.key, ALL_SUITES, [(r.score, r.usage) for r in usable])
        by_repeat.setdefault(run.repeat, []).append(overall)
        if run.repeat == 0:
            stage.summaries[run.config.key] = {ALL_SUITES: overall, **suites}
    first = [s[ALL_SUITES] for s in stage.summaries.values()]
    stage.composites = composites(first)
    for summaries in by_repeat.values():
        for key, comp in composites(summaries).items():
            stage.repeat_totals.setdefault(key, []).append(comp.total)
    stage.spread = {k: mean_std(v) for k, v in stage.repeat_totals.items()}
