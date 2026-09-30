"""Scores a stored bake-off run again with the scorer as it is now, without any model call.

A run's JSON record keeps every case's gold and every drafted concept, relation and attribute,
so when the scorer changes (a label rule, a synonym) the record is scored again and the numbers
of two runs made under different scorers become comparable. Prints, per configuration, the
totals the speech tuning reports use, before and after, and writes them as JSON when `--out`
is given.

    uv run python -m evals.rescore results/r5-learn-gpt.json --out results/rescored.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evals.input_modes import DocumentCache, document_text
from evals.scoring import (
    CaseScore,
    PredictedAttribute,
    PredictedConcept,
    PredictedRelation,
    f1,
    score_case,
)
from evals.teach_case import TeachCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Totals:
    """The sums a comparison reads: over every scored case of one configuration."""

    cases: int = 0
    expected: int = 0
    matched: int = 0
    parent_at_depth: int = 0
    verb_correct: int = 0
    relations_expected: int = 0
    relations_correct: int = 0
    invented: int = 0
    missed: int = 0
    concept_f1: float = 0.0
    changed_cases: list[str] = field(default_factory=list)

    def add(self, score: CaseScore | dict[str, Any]) -> None:
        get = score.get if isinstance(score, dict) else lambda k: getattr(score, k)
        self.cases += 1
        self.expected += get("concepts_expected")
        self.matched += get("concepts_matched")
        self.parent_at_depth += get("parent_at_depth")
        self.verb_correct += get("action_correct")
        self.relations_expected += get("relations_expected")
        self.relations_correct += get("relation_action_correct")
        self.invented += len(get("invented"))
        self.missed += len(get("missed"))

    def finish(self) -> Totals:
        precision = self.matched / (self.matched + self.invented) if self.matched else 0.0
        recall = self.matched / self.expected if self.expected else 0.0
        self.concept_f1 = round(f1(precision, recall), 4)
        return self


async def rescore(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per configuration key: the stored totals (`before`) and the totals under the current
    scorer (`after`), with the cases whose parent-at-depth or invented count moved."""
    cases = {c["id"]: _case(c) for c in record["cases"]}
    docs = DocumentCache()
    out: dict[str, dict[str, Any]] = {}
    for stage in record["stages"]:
        for run in stage["runs"]:
            key = run["config"]["key"] if "key" in run["config"] else _key(run["config"])
            before = Totals()
            after = Totals()
            for r in run["results"]:
                if r.get("score") is None or r.get("skipped"):
                    continue
                case = cases[r["case_id"]]
                try:
                    source = await document_text(case, docs)
                except FileNotFoundError:
                    continue
                concepts = [PredictedConcept(**c) for c in r["concepts"]]
                relations = [PredictedRelation(**c) for c in r["relations"]]
                attributes = [PredictedAttribute(**c) for c in r.get("attributes", [])]
                fresh = score_case(case, concepts, relations, source, attributes)
                before.add(r["score"])
                after.add(fresh)
                moved = (fresh.parent_at_depth, len(fresh.invented), len(fresh.missed)) != (
                    r["score"]["parent_at_depth"],
                    len(r["score"]["invented"]),
                    len(r["score"]["missed"]),
                )
                if moved:
                    after.changed_cases.append(
                        f"{r['case_id']}: parent at depth {r['score']['parent_at_depth']} to "
                        f"{fresh.parent_at_depth}, invented {len(r['score']['invented'])} to "
                        f"{len(fresh.invented)}, missed {len(r['score']['missed'])} to "
                        f"{len(fresh.missed)}"
                    )
            out[key] = {"before": asdict(before.finish()), "after": asdict(after.finish())}
    return out


def _case(data: dict[str, Any]) -> TeachCase:
    """The case as recorded; a document path recorded relative to the repository root is
    resolved against it, so a record made from another working directory still reads."""
    case = TeachCase.model_validate(data)
    if case.document is not None and not case.document.exists():
        rooted = REPOSITORY_ROOT / case.document
        if rooted.exists():
            case = case.model_copy(update={"document": rooted})
    return case


def _key(config: dict[str, Any]) -> str:
    return f"{config['deployment']}@{config['effort']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("record", type=Path, help="a run's JSON record")
    parser.add_argument("--out", type=Path, help="write the totals as JSON")
    args = parser.parse_args(argv)
    record = json.loads(args.record.read_text(encoding="utf-8"))
    totals = asyncio.run(rescore(record))
    for key, both in totals.items():
        for label in ("before", "after"):
            t = both[label]
            print(
                f"{key} {label}: {t['cases']} cases, parent at depth "
                f"{t['parent_at_depth']}/{t['expected']}, verb {t['verb_correct']}/{t['matched']}, "
                f"relations {t['relations_correct']}/{t['relations_expected']}, invented "
                f"{t['invented']}, missed {t['missed']}, concept F1 {t['concept_f1']}"
            )
        for line in both["after"]["changed_cases"]:
            print(f"  {line}")
    if args.out:
        args.out.write_text(json.dumps(totals, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
