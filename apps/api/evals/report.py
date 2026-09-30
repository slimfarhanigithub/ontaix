"""The bake-off's markdown report and its JSON record."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from evals.aggregate import RunSummary
from evals.stages import ALL_SUITES, StageResult
from evals.teach_case import TeachCase


@dataclasses.dataclass
class RunRecord:
    """Everything one invocation of the bake-off produced."""

    started_at: str
    dry_run: bool
    budget_eur: float
    spent_eur: float
    estimate: dict[str, Any]
    cases: list[TeachCase]
    notes: list[str]
    documents: list[dict[str, Any]]
    stages: list[StageResult]


def write(record: RunRecord, json_path: Path, markdown_path: Path) -> None:
    plain = _plain(record)
    plain["speechComprehension"] = {s.name: speech_rows(s) for s in record.stages}
    plain["reviewPass"] = {s.name: review_rows(s) for s in record.stages}
    json_path.write_text(
        json.dumps(plain, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    markdown_path.write_text(markdown(record), encoding="utf-8", newline="\n")


def markdown(record: RunRecord) -> str:
    lines = [
        "# Teach Bake-Off Report",
        "",
        f"Started {record.started_at}. {'Dry run with fake clients. ' if record.dry_run else ''}"
        f"Spent {record.spent_eur:.4f} EUR of a {record.budget_eur:.2f} EUR budget "
        f"(estimate before the run: {record.estimate.get('totalEur', 0):.2f} EUR).",
        "",
    ]
    for stage in record.stages:
        lines += _stage(stage)
        lines += _speech(stage)
        lines += _review(stage)
    lines += _cases(record)
    lines += _documents(record)
    if record.notes:
        lines += ["## Notes", "", *[f"- {n}" for n in record.notes], ""]
    return "\n".join(lines)


def _stage(stage: StageResult) -> list[str]:
    title = stage.name.title()
    lines = [f"## {title}", ""]
    if stage.stopped_by_budget:
        lines += ["The budget was spent: this stage stopped before every case ran.", ""]
    ranked = sorted(stage.composites.values(), key=lambda c: -c.total)
    modes = {r.config.key: r.capabilities.get("outputMode", "-") for r in stage.runs}
    residency = {r.config.key: r.config.residency for r in stage.runs}
    lines += [
        f"### {title} Ranking",
        "",
        "| # | Configuration | Residency | Composite | Precision block | Recall block | "
        "Efficiency | "
        "Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | "
        "Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, comp in enumerate(ranked, start=1):
        s = stage.summaries[comp.run_key][ALL_SUITES]
        spread = stage.spread.get(comp.run_key)
        total = f"{comp.total:.3f}"
        if spread and len(stage.repeat_totals.get(comp.run_key, [])) > 1:
            total = f"{spread[0]:.3f} ± {spread[1]:.3f}"
        lines.append(
            f"| {i} | {comp.run_key} | {residency.get(comp.run_key, '-')} | {total} | "
            f"{comp.precision:.3f} | {comp.recall:.3f} | "
            f"{comp.efficiency:.3f} | {_pct(s.concept_precision)} | {_pct(s.recall_groundable)} "
            f"| {_pct(s.parent_accuracy)} | {_pct(s.action_accuracy)} | {_pct(s.path_accuracy)} "
            f"| {s.invented} | {s.missed} | {_pct(s.mean_level_f1)} | {s.degraded_units} | "
            f"{s.errors} | {s.calls} | {s.cost_eur:.4f} | {s.mean_latency_s:.1f} | "
            f"{s.p95_latency_s:.1f} | {modes.get(comp.run_key, '-')} |"
        )
    lines.append("")
    withheld = sorted({(r.config.key, len(r.withheld)) for r in stage.runs if r.withheld})
    if withheld:
        lines += [
            "Private cases withheld from global (non EU data zone) models: "
            + ", ".join(f"{k} ({n})" for k, n in withheld)
            + ".",
            "",
        ]
    lines += _suites(stage, ranked)
    lines += _levels(stage, ranked)
    if stage.paired:
        lines += [
            f"### {title} Against The Baseline",
            "",
            "Case-level concept F1 against groundable concepts, each case's mean over repeats, "
            "minus the baseline's.",
            "",
            "| Configuration | Baseline | Cases | Mean difference | 95% CI | Wins / ties / losses "
            "| Sign test p |",
            "|---|---|---|---|---|---|---|",
        ]
        for p in sorted(stage.paired, key=lambda p: -p.mean_diff):
            lines.append(
                f"| {p.run_key} | {p.baseline} | {p.cases} | {p.mean_diff:+.3f} | "
                f"[{p.ci95_low:+.3f}, {p.ci95_high:+.3f}] | {p.wins} / {p.ties} / {p.losses} | "
                f"{p.sign_test_p:.3f} |"
            )
        lines.append("")
    return lines


def speech_rows(stage: StageResult) -> list[dict[str, Any]]:
    """Speech comprehension per scored speech case, configuration and repeat: the recording's
    final drafts against the gold tree."""
    rows: list[dict[str, Any]] = []
    for run in stage.runs:
        for r in run.results:
            s = r.score
            if r.kind != "speech" or s is None:
                continue
            rows.append(
                {
                    "case": r.case_id,
                    "configuration": r.run_key,
                    "repeat": r.repeat,
                    "sentences": len(r.units),
                    "expected": s.concepts_expected,
                    "matched": s.concepts_matched,
                    "parentAtDepth": s.parent_at_depth,
                    "parentAtDepthRate": _ratio(s.parent_at_depth, s.concepts_expected),
                    "verbCorrect": s.action_correct,
                    "verbAccuracy": _ratio(s.action_correct, s.concepts_matched),
                    "relationsExpected": s.relations_expected,
                    "relationVerbCorrect": s.relation_action_correct,
                    "relationAccuracy": _ratio(s.relation_action_correct, s.relations_expected),
                    "attributesExpected": s.attributes_expected,
                    "attributesMatched": s.attributes_matched,
                    "inventedAttributes": list(s.invented_attributes),
                    "missedAttributes": list(s.missed_attributes),
                    "depthReached": s.depth_achieved,
                    "depthGold": s.depth_expected,
                    "invented": list(s.invented),
                    "missed": list(s.missed),
                    "wrongParent": list(s.wrong_parent),
                    "wrongDepth": list(s.wrong_depth),
                    "wrongVerb": list(s.wrong_action),
                    "failedSentences": sum(1 for u in r.units if u.status != 200),
                }
            )
    return sorted(rows, key=lambda row: (row["case"], row["configuration"], row["repeat"]))


def _speech(stage: StageResult) -> list[str]:
    rows = speech_rows(stage)
    if not rows:
        return []
    lines = [
        f"### {stage.name.title()} Speech Comprehension",
        "",
        "Each recording is sent sentence by sentence as `speech` in one session; its final "
        "drafts are scored against the gold tree. Parent at depth: expected concepts drafted "
        "under an accepted parent at the expected level. Verb: matched concepts with an "
        "accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: "
        "expected taught attributes drafted on the right concept with an accepted value.",
        "",
        "| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | "
        "Attribute | Depth reached / gold | Invented | Missed |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        relation = (
            f"{row['relationVerbCorrect']}/{row['relationsExpected']}"
            if row["relationsExpected"]
            else "-"
        )
        attribute = (
            f"{row['attributesMatched']}/{row['attributesExpected']}"
            if row["attributesExpected"]
            else "-"
        )
        lines.append(
            f"| {row['case']} | {row['configuration']} | {row['repeat']} | {row['sentences']} | "
            f"{row['parentAtDepth']}/{row['expected']} | {row['verbCorrect']}/{row['matched']} "
            f"| {relation} | {attribute} | {row['depthReached']} / {row['depthGold']} | "
            f"{_labels(row['invented'])} | {_labels(row['missed'])} |"
        )
    return [*lines, ""]


def review_rows(stage: StageResult) -> list[dict[str, Any]]:
    """The reviewer's pass over each scored speech case: the recording's scores before and
    after its corrections, what became of the corrections, and the review's cost."""
    rows: list[dict[str, Any]] = []
    for run in stage.runs:
        for r in run.results:
            v = r.review
            if v is None or v.before is None:
                continue
            after = v.after or v.before
            rows.append(
                {
                    "case": r.case_id,
                    "configuration": r.run_key,
                    "repeat": r.repeat,
                    "sentences": len(r.units),
                    "expected": v.before.concepts_expected,
                    "parentAtDepthBefore": v.before.parent_at_depth,
                    "parentAtDepthAfter": after.parent_at_depth,
                    "inventedBefore": len(v.before.invented),
                    "inventedAfter": len(after.invented),
                    "missedBefore": len(v.before.missed),
                    "missedAfter": len(after.missed),
                    "relationsBefore": v.before.relation_action_correct,
                    "relationsAfter": after.relation_action_correct,
                    "relationsExpected": v.before.relations_expected,
                    "corrections": v.corrections,
                    "applied": v.applied,
                    "refused": dict(v.refused),
                    "inputTokens": v.input_tokens,
                    "outputTokens": v.output_tokens,
                    "costEur": v.cost_eur,
                    "latencyMs": v.latency_ms,
                    "error": v.error,
                }
            )
    return sorted(rows, key=lambda row: (row["case"], row["configuration"], row["repeat"]))


def _review(stage: StageResult) -> list[str]:
    rows = review_rows(stage)
    if not rows:
        return []
    lines = [
        f"### {stage.name.title()} Review Pass",
        "",
        "The deeper model reviews each scored recording's drafts after the run's own model and "
        "returns corrections (rename, delete, move, add), applied to the drafted tree with "
        "every new label grounded in the recording; the recording is scored again. Cost and "
        "time are the review's own, apart from the run's model.",
        "",
        "| Case | Configuration | Sentences | Parent at depth | Invented | Missed | Relations | "
        "Corrections (applied / refused) | Cost EUR | s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        refused = sum(row["refused"].values())
        note = f" ({row['error']})" if row["error"] else ""
        lines.append(
            f"| {row['case']} | {row['configuration']} | {row['sentences']} | "
            f"{row['parentAtDepthBefore']} to {row['parentAtDepthAfter']} of {row['expected']} | "
            f"{row['inventedBefore']} to {row['inventedAfter']} | "
            f"{row['missedBefore']} to {row['missedAfter']} | "
            f"{row['relationsBefore']} to {row['relationsAfter']} of {row['relationsExpected']} | "
            f"{row['corrections']} ({row['applied']} / {refused}){note} | {row['costEur']:.4f} | "
            f"{row['latencyMs'] / 1000:.1f} |"
        )
    total_cost = sum(row["costEur"] for row in rows)
    sentences = sum(row["sentences"] for row in rows)
    before = sum(row["parentAtDepthBefore"] for row in rows)
    after = sum(row["parentAtDepthAfter"] for row in rows)
    expected = sum(row["expected"] for row in rows)
    lines += [
        "",
        f"Over {len(rows)} recordings and {sentences} sentences: parent at depth {before} to "
        f"{after} of {expected}, invented {sum(r['inventedBefore'] for r in rows)} to "
        f"{sum(r['inventedAfter'] for r in rows)}, missed {sum(r['missedBefore'] for r in rows)} "
        f"to {sum(r['missedAfter'] for r in rows)}; review cost {total_cost:.4f} EUR, "
        f"{(total_cost / sentences if sentences else 0):.4f} EUR per reviewed sentence.",
        "",
    ]
    return lines


def _labels(labels: list[str]) -> str:
    return ", ".join(labels) if labels else "-"


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def _suites(stage: StageResult, ranked: list) -> list[str]:
    suites = sorted({s for per in stage.summaries.values() for s in per if s != ALL_SUITES})
    if not suites:
        return []
    lines = [
        f"### {stage.name.title()} By Suite",
        "",
        "Concept F1 against groundable concepts / path accuracy / cost EUR, per suite "
        "(origin:mode).",
        "",
        "| Configuration | " + " | ".join(suites) + " |",
        "|---|" + "---|" * len(suites),
    ]
    for comp in ranked:
        per = stage.summaries[comp.run_key]
        cells = [_suite_cell(per[suite]) if suite in per else "-" for suite in suites]
        lines.append(f"| {comp.run_key} | " + " | ".join(cells) + " |")
    return [*lines, ""]


def _suite_cell(s: RunSummary) -> str:
    if not s.scored:
        return f"report-only / {s.cost_eur:.3f}"
    return f"{_pct(s.f1_groundable)} / {_pct(s.path_accuracy)} / {s.cost_eur:.3f}"


def _levels(stage: StageResult, ranked: list) -> list[str]:
    levels = sorted({lv for per in stage.summaries.values() for lv in per[ALL_SUITES].levels})
    if not levels:
        return []
    lines = [
        f"### {stage.name.title()} Per Level",
        "",
        "F1 of right-path concepts per tree level (1 = child of the company root), every level "
        "present. Expected counts in the header.",
        "",
    ]
    first = stage.summaries[ranked[0].run_key][ALL_SUITES] if ranked else None
    header = [
        f"L{lv} ({first.levels[lv].expected if first and lv in first.levels else 0})"
        for lv in levels
    ]
    lines += ["| Configuration | " + " | ".join(header) + " |", "|---|" + "---|" * len(levels)]
    for comp in ranked:
        s = stage.summaries[comp.run_key][ALL_SUITES]
        cells = [_pct(s.levels[lv].f1) if lv in s.levels else "-" for lv in levels]
        lines.append(f"| {comp.run_key} | " + " | ".join(cells) + " |")
    return [*lines, ""]


def _cases(record: RunRecord) -> list[str]:
    lines = [
        "## Cases",
        "",
        "| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |",
        "|---|---|---|---|---|---|",
    ]
    ceilings = _ceilings(record)
    for c in record.cases:
        expected = c.expected
        lines.append(
            f"| {c.id} | {c.origin} | {c.kind} | "
            f"{len(expected.concepts) if expected else 'report-only'} | "
            f"{len(expected.relations) if expected else '-'} | {ceilings.get(c.id, '-')} |"
        )
    reports = [c for c in record.cases if c.source_report]
    if reports:
        lines += ["", "### Gold Tree Reports", ""]
        for c in reports:
            lines.append(f"- {c.id}: `{json.dumps(c.source_report, default=str)[:600]}`")
    return [*lines, ""]


def _documents(record: RunRecord) -> list[str]:
    if not record.documents:
        return []
    lines = [
        "## Documents And OCR",
        "",
        "OCR runs once per scanned document, before and apart from the model runs.",
        "",
        "| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in record.documents:
        ocr = d.get("ocr") or {}
        lines.append(
            f"| {Path(str(d['path'])).name} | {d['format']} | {d['words']} | "
            f"{d.get('pages') or '-'} | {ocr.get('deployment', '-')} | {ocr.get('pages', '-')} | "
            f"{(ocr.get('latency_ms', 0) or 0) / 1000:.1f} | {ocr.get('cost_eur', 0) or 0:.4f} |"
        )
    return [*lines, ""]


def _ceilings(record: RunRecord) -> dict[str, str]:
    out: dict[str, str] = {}
    for stage in record.stages:
        for run in stage.runs:
            for r in run.results:
                if r.score is not None and r.case_id not in out:
                    out[r.case_id] = _pct(r.score.grounding_ceiling)
    return out


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value
