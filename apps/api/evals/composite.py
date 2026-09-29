"""The composite score that ranks run configurations, and the statistics of repeated runs.

The composite weights precision first, then recall and depth, then speed and cost:

- precision block (weight 0.5): concept precision (invented nodes lower it) 50 %, parent
  accuracy 25 %, verb accuracy 25 %;
- recall block (weight 0.3): recall against groundable concepts 50 %, mean per-level F1 over
  every level present 50 %;
- efficiency block (weight 0.2): latency 50 % and cost per case 50 %, each as the best value
  among the compared configurations divided by this one's, so the fastest and the cheapest
  score 1; a model without a price scores 0.5 on cost.

A configuration with no scored case scores 0 on the quality blocks. Pure functions: no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from evals.aggregate import RunSummary

PRECISION_WEIGHT = 0.5
RECALL_WEIGHT = 0.3
EFFICIENCY_WEIGHT = 0.2
UNPRICED_COST_SCORE = 0.5


@dataclass(frozen=True)
class Composite:
    run_key: str
    precision: float
    recall: float
    efficiency: float
    total: float


@dataclass(frozen=True)
class Paired:
    """A configuration against the baseline, case by case (each case's mean over repeats)."""

    run_key: str
    baseline: str
    cases: int
    mean_diff: float
    ci95_low: float
    ci95_high: float
    wins: int
    ties: int
    losses: int
    sign_test_p: float


def composites(summaries: list[RunSummary]) -> dict[str, Composite]:
    """Composite scores of configurations compared together (one summary each)."""
    latencies = [s.mean_latency_s for s in summaries if s.mean_latency_s > 0]
    costs = [s.cost_per_case for s in summaries if s.cost_per_case > 0]
    best_latency, best_cost = min(latencies, default=0.0), min(costs, default=0.0)
    out: dict[str, Composite] = {}
    for s in summaries:
        if s.scored:
            precision = 0.5 * s.concept_precision + 0.25 * s.parent_accuracy
            precision += 0.25 * s.action_accuracy
            recall = 0.5 * s.recall_groundable + 0.5 * s.mean_level_f1
        else:
            precision = recall = 0.0
        latency = best_latency / s.mean_latency_s if s.mean_latency_s > 0 else 1.0
        if s.cost_per_case > 0:
            cost = best_cost / s.cost_per_case
        else:
            # Calls with no cost come from a model without a price: neutral, not the cheapest.
            cost = UNPRICED_COST_SCORE if s.calls else 1.0
        efficiency = 0.5 * latency + 0.5 * cost
        total = (
            PRECISION_WEIGHT * precision + RECALL_WEIGHT * recall + EFFICIENCY_WEIGHT * efficiency
        )
        out[s.run_key] = Composite(s.run_key, precision, recall, efficiency, total)
    return out


def mean_std(values: list[float]) -> tuple[float, float]:
    """Mean and sample standard deviation (0 for fewer than two values)."""
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def paired(
    run_key: str, baseline_key: str, ours: dict[str, float], theirs: dict[str, float]
) -> Paired:
    """`ours` against `theirs` on the cases both scored; differences are ours minus theirs."""
    common = sorted(set(ours) & set(theirs))
    diffs = [ours[c] - theirs[c] for c in common]
    mean, std = mean_std(diffs)
    half = 1.96 * std / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
    wins = sum(1 for d in diffs if d > 1e-9)
    losses = sum(1 for d in diffs if d < -1e-9)
    return Paired(
        run_key=run_key,
        baseline=baseline_key,
        cases=len(diffs),
        mean_diff=mean,
        ci95_low=mean - half,
        ci95_high=mean + half,
        wins=wins,
        ties=len(diffs) - wins - losses,
        losses=losses,
        sign_test_p=sign_test(wins, losses),
    )


def sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test p-value; ties are left out."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)
