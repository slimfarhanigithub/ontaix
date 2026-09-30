"""Runs one case in one input mode through the teach pipeline and scores what it drafted."""

from __future__ import annotations

import logging
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import httpx

from evals.aggregate import CaseUsage
from evals.input_modes import DocumentCache, InputMode, ModeUnavailable
from evals.recording_llm_client import RecordedCall, record_calls
from evals.scoring import (
    CaseScore,
    PredictedAttribute,
    PredictedConcept,
    PredictedRelation,
    drafted_depth,
    score_case,
)
from evals.teach_case import TeachCase
from evals.workspace import UnitResult, Workspace

logger = logging.getLogger(__name__)

IS_A = "is a"


@dataclass
class CaseResult:
    case_id: str
    kind: str
    origin: str
    mode: str
    run_key: str
    repeat: int
    units: list[UnitResult] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)
    usage: CaseUsage = field(default_factory=CaseUsage)
    concepts: list[PredictedConcept] = field(default_factory=list)
    relations: list[PredictedRelation] = field(default_factory=list)
    attributes: list[PredictedAttribute] = field(default_factory=list)
    other_drafts: int = 0
    score: CaseScore | None = None
    drafted_depth: int = 0
    document: dict[str, Any] | None = None
    skipped: str | None = None
    error: str | None = None
    wall_ms: int = 0

    @property
    def suite(self) -> str:
        return f"{self.origin}:{self.mode}"


async def run_case(
    client: httpx.AsyncClient,
    case: TeachCase,
    mode: InputMode,
    docs: DocumentCache,
    run_key: str,
    repeat: int,
) -> CaseResult:
    """Never raises: a failure is recorded on the result."""
    result = CaseResult(case.id, case.kind, case.origin, mode.name, run_key, repeat)
    result.calls = record_calls()
    started = time.monotonic()
    try:
        ws = Workspace(client, case)
        await ws.open()
        output = await mode.run(ws, case, docs)
        result.units, result.document = output.units, output.document
        labels = await ws.labels()
        drafts = [d for u in output.units for d in u.drafts]
        predicted = predictions(drafts, labels)
        result.concepts, result.relations, result.attributes, result.other_drafts = predicted
        if case.expected is not None:
            result.score = score_case(
                case, result.concepts, result.relations, output.source_text, result.attributes
            )
        result.drafted_depth = drafted_depth(case, result.concepts)
    except ModeUnavailable as exc:
        result.skipped = str(exc)
    except Exception as exc:
        logger.warning("case %s failed in %s: %s", case.id, mode.name, exc)
        result.error = f"{type(exc).__name__}: {exc}"[:500]
        logger.debug("%s", traceback.format_exc())
    result.wall_ms = int((time.monotonic() - started) * 1000)
    result.usage = usage_of(result)
    return result


def predictions(
    drafts: list[dict[str, Any]], labels: dict[str, str]
) -> tuple[list[PredictedConcept], list[PredictedRelation], list[PredictedAttribute], int]:
    """Drafted concepts, specs, relations and taught attributes with every id turned into its
    label."""
    concepts: list[PredictedConcept] = []
    relations: list[PredictedRelation] = []
    attributes: list[PredictedAttribute] = []
    other = 0

    def label(concept_id: str | None, fallback: str | None) -> str:
        return labels.get(concept_id or "", "") or (fallback or "")

    for d in drafts:
        kind = d.get("type")
        if kind == "concept":
            concepts.append(
                PredictedConcept(
                    d["label"],
                    label(d.get("parentId"), d.get("parentLabel")),
                    d.get("action") or "",
                    bool(d.get("reverse")),
                )
            )
        elif kind == "spec":
            parent = label(d.get("parentId"), d.get("parentLabel"))
            concepts.append(PredictedConcept(d["label"], parent, IS_A))
        elif kind == "relation":
            relations.append(
                PredictedRelation(
                    label(d.get("aId"), d.get("aLabel")),
                    label(d.get("bId"), d.get("bLabel")),
                    d.get("action") or "",
                )
            )
        elif kind == "attr" and d.get("value") is not None:
            attributes.append(
                PredictedAttribute(
                    label(d.get("conceptId"), d.get("conceptLabel")),
                    d.get("name") or "",
                    d["value"],
                )
            )
        else:
            other += 1
    return concepts, relations, attributes, other


def usage_of(result: CaseResult) -> CaseUsage:
    outcomes = Counter(u.llm_outcome or "none" for u in result.units)
    extractors = Counter(u.extractor or "none" for u in result.units)
    return CaseUsage(
        units=len(result.units),
        calls=len(result.calls),
        input_tokens=sum(c.input_tokens for c in result.calls),
        output_tokens=sum(c.output_tokens for c in result.calls),
        cost_eur=round(sum(c.cost_eur for c in result.calls), 6),
        latencies_ms=[c.latency_ms for c in result.calls],
        degraded_units=sum(1 for u in result.units if u.degraded),
        unresolved=sum(len(u.unresolved) for u in result.units),
        llm_outcomes=dict(outcomes),
        extractors=dict(extractors),
        error=result.error,
    )
