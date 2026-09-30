"""Summaries of bake-off results: one per run configuration and suite, or over all suites.

Concept and relation precision, recall and F1 are micro-averaged over the scored cases; parent,
action and path accuracy are over matched concepts; recall is also given against groundable
concepts only (labels the source text contains). Levels are summed over cases and reported for
every level present, with no depth limit. Cost and latency cover every case, scored or not, and
so do the stage timings: the median, 90th percentile and slowest of every stage each parse of
the pipeline published, so a change in latency is placed in the stage that caused it.
Pure functions: no I/O.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from app.utilities.stage_clock import StageTimings
from evals.scoring import CaseScore, f1


@dataclass
class CaseUsage:
    """What one case cost in one run: model calls, tokens, euros, latency and pipeline flags."""

    units: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    latencies_ms: list[int] = field(default_factory=list)
    degraded_units: int = 0
    unresolved: int = 0
    llm_outcomes: dict[str, int] = field(default_factory=dict)
    extractors: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    # The provider's time to its first answer fragment, per streamed call.
    first_token_ms: list[int] = field(default_factory=list)
    timings: list[StageTimings] = field(default_factory=list)


@dataclass
class StagePercentiles:
    """One stage over every parse of a run: how many parses ran it, and its milliseconds at the
    median, the 90th percentile and the slowest."""

    count: int
    p50_ms: int
    p90_ms: int
    max_ms: int


@dataclass
class LevelSummary:
    expected: int
    groundable: int
    predicted: int
    correct: int
    precision: float
    recall: float
    recall_groundable: float
    f1: float


@dataclass
class RunSummary:
    run_key: str
    suite: str
    cases: int
    scored: int
    concept_precision: float
    concept_recall: float
    concept_f1: float
    recall_groundable: float
    f1_groundable: float
    grounding_ceiling: float
    parent_accuracy: float
    action_accuracy: float
    path_accuracy: float
    relation_precision: float
    relation_recall: float
    relation_f1: float
    invented: int
    duplicates: int
    missed: int
    depth_ratio: float
    levels: dict[int, LevelSummary]
    mean_level_f1: float
    degraded_units: int
    unresolved: int
    errors: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_eur: float
    cost_per_case: float
    mean_latency_s: float
    p95_latency_s: float
    llm_outcomes: dict[str, int]
    # Per clock name (`parse`, `extraction`), per stage, in the order the stages first ended.
    stage_timings: dict[str, dict[str, StagePercentiles]] = field(default_factory=dict)


def summarise(
    run_key: str, suite: str, items: list[tuple[CaseScore | None, CaseUsage]]
) -> RunSummary:
    scores = [s for s, _ in items if s is not None]
    usages = [u for _, u in items]
    matched = sum(s.concepts_matched for s in scores)
    invented = sum(len(s.invented) for s in scores)
    expected = sum(s.concepts_expected for s in scores)
    groundable = sum(s.concepts_groundable for s in scores)
    precision, recall = _ratio(matched, matched + invented), _ratio(matched, expected)
    recall_g = _ratio(sum(s.matched_groundable for s in scores), groundable)
    rel_matched = sum(s.relations_matched for s in scores)
    rel_predicted = sum(s.relations_matched + len(s.invented_relations) for s in scores)
    rel_p = _ratio(rel_matched, rel_predicted)
    rel_r = _ratio(rel_matched, sum(s.relations_expected for s in scores))
    levels = _levels(scores)
    latencies = sorted(ms for u in usages for ms in u.latencies_ms)
    outcomes: Counter[str] = Counter()
    for u in usages:
        outcomes.update(u.llm_outcomes)
    cost = round(sum(u.cost_eur for u in usages), 6)
    return RunSummary(
        run_key=run_key,
        suite=suite,
        cases=len(items),
        scored=len(scores),
        concept_precision=precision,
        concept_recall=recall,
        concept_f1=f1(precision, recall),
        recall_groundable=recall_g,
        f1_groundable=f1(precision, recall_g),
        grounding_ceiling=_ratio(groundable, expected),
        parent_accuracy=_ratio(sum(s.parent_correct for s in scores), matched),
        action_accuracy=_ratio(sum(s.action_correct for s in scores), matched),
        path_accuracy=_ratio(sum(s.path_correct for s in scores), matched),
        relation_precision=rel_p,
        relation_recall=rel_r,
        relation_f1=f1(rel_p, rel_r),
        invented=invented,
        duplicates=sum(len(s.duplicates) for s in scores),
        missed=sum(len(s.missed) for s in scores),
        depth_ratio=_mean(
            [min(1.0, s.depth_achieved / s.depth_expected) for s in scores if s.depth_expected]
        ),
        levels=levels,
        mean_level_f1=_mean([lv.f1 for lv in levels.values() if lv.expected]),
        degraded_units=sum(u.degraded_units for u in usages),
        unresolved=sum(u.unresolved for u in usages),
        errors=sum(1 for u in usages if u.error),
        calls=sum(u.calls for u in usages),
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        cost_eur=cost,
        cost_per_case=cost / len(items) if items else 0.0,
        mean_latency_s=_mean(latencies) / 1000,
        p95_latency_s=_percentile(latencies, 0.95) / 1000,
        llm_outcomes=dict(sorted(outcomes.items())),
        stage_timings=stage_percentiles([t for u in usages for t in u.timings]),
    )


def stage_percentiles(timings: list[StageTimings]) -> dict[str, dict[str, StagePercentiles]]:
    """Every stage of every clock name in `timings`, with its percentiles over the parses that
    ran it; counters (`input_tokens`, `output_tokens`) are summarised the same way."""
    values: dict[str, dict[str, list[int]]] = {}
    for t in timings:
        per_stage = values.setdefault(t.name, {})
        for stage, ms in [*t.stages.items(), *t.counts.items()]:
            per_stage.setdefault(stage, []).append(ms)
    out: dict[str, dict[str, StagePercentiles]] = {}
    for name, per_stage in values.items():
        out[name] = {}
        for stage, samples in per_stage.items():
            ordered = sorted(samples)
            out[name][stage] = StagePercentiles(
                len(ordered),
                int(_percentile(ordered, 0.5)),
                int(_percentile(ordered, 0.9)),
                ordered[-1],
            )
    return out


def _levels(scores: list[CaseScore]) -> dict[int, LevelSummary]:
    totals: dict[int, list[int]] = {}
    for s in scores:
        for level, lv in s.levels.items():
            t = totals.setdefault(level, [0, 0, 0, 0, 0])
            t[0] += lv.expected
            t[1] += lv.groundable
            t[2] += lv.predicted
            t[3] += lv.correct
            t[4] += lv.correct_groundable
    out: dict[int, LevelSummary] = {}
    for level in sorted(totals):
        exp, grd, pred, cor, cor_g = totals[level]
        p, r = _ratio(cor, pred), _ratio(cor, exp)
        out[level] = LevelSummary(exp, grd, pred, cor, p, r, _ratio(cor_g, grd), f1(p, r))
    return out


def _ratio(num: int, den: int) -> float:
    return 1.0 if den == 0 else num / den


def _mean(values: list[float] | list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: list[int], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, math.ceil(q * len(sorted_values)) - 1)
    return float(sorted_values[index])
