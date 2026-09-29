"""The last step of a whole-document extraction job: the outline and the section intents mapped
to one draft tree, parents first and relations last.

Each outline node the company does not hold yet becomes a `ConceptDraft` born from its parent -
an existing concept by id, an earlier node by label - with the node's action. Section intents go
through the teach grammar's mapping table, citing outline nodes by label. A label that matches a
concept of the company reuses it, a fact the outline or the model already holds produces no
draft, and drafts stop at the job's node ceiling; what is left is listed as unresolved. Every
note keeps its grounding sentence's `originDetail`, so proposals survive the import's purge.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models.api.teach import DraftNote
from app.models.storage.concept import Concept
from app.services.document_extraction_pass_service import (
    DEFAULT_DOMAIN,
    INTENT,
    Outline,
    label_key,
)
from app.services.document_extraction_service import ORIGIN_DETAIL
from app.services.ontology_view_service import OntologyView
from app.services.teach_draft_service import Drafter, End
from app.utilities.action_text import normalise_action

logger = logging.getLogger(__name__)

MAX_EXPLANATION = 120
MAX_UNRESOLVED = 5000


@dataclass
class Mapped:
    drafts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False


def map_tree(
    view: OntologyView,
    company_id: uuid.UUID,
    entries: list[dict[str, Any]],
    origin_details: dict[int, dict[str, Any]],
    ceiling: int,
) -> Mapped:
    outline = Outline(view, company_id, list(entries))
    drafter = Drafter(view, company_id, outline.root, None, {})
    out = Mapped()
    # Label key -> (draft index, drafted label, depth) of each concept or spec draft.
    drafted: dict[str, tuple[int, str, int]] = {}
    # Node index -> the concept it stands for, the drafted label, or None when it was dropped.
    placed: dict[int, End | None] = {}
    births: set[tuple[str, str, str]] = set()
    company = str(company_id)

    def full() -> bool:
        return len(out.drafts) >= ceiling

    for node in outline.nodes:
        index = node["index"]
        existing = _existing(outline, node)
        if existing is not None:
            placed[index] = End(existing, existing.label, existing.label)
            continue
        parent = _parent_end(outline, node, placed)
        if parent is None or full():
            placed[index] = None
            reason = "node_ceiling" if full() else "unknown_parent"
            out.degraded = out.degraded or full()
            _drop(out, node["chunk"], node["sentenceIndex"], reason, node["label"])
            continue
        draft: dict[str, Any] = {"type": "concept", "companyId": company}
        requires: list[int] = []
        if parent.concept is not None:
            draft["parentId"] = str(parent.concept.id)
            depth = len(view.ancestors_of(parent.concept.id)) + 1
        else:
            parent_index, parent_label, parent_depth = drafted[label_key(parent.label)]
            draft["parentLabel"] = parent_label
            requires.append(parent_index)
            depth = parent_depth + 1
        draft.update(
            label=node["label"],
            domainKey=node.get("domainKey") or DEFAULT_DOMAIN,
            action=node["action"],
            reverse=False,
        )
        drafted[label_key(node["label"])] = (len(out.drafts), node["label"], depth)
        drafter.introduced.setdefault(node["label"].lower(), (node["label"], draft["domainKey"]))
        births.add((_side(parent), node["action"], node["label"].lower()))
        out.drafts.append(draft)
        span = node.get("span")
        out.notes.append(
            _note(
                "outline",
                node["confidence"],
                None,
                node["role"],
                depth,
                requires,
                node["sentenceIndex"],
                span,
                origin_details,
            )
        )
        placed[index] = End(None, node["label"], node["label"])

    relations: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        if entry.get("kind") != INTENT:
            continue
        sentence_index = entry["sentenceIndex"]
        if full():
            out.degraded = True
            _drop(out, entry["chunk"], sentence_index, "node_ceiling")
            continue
        subject = _end(outline, drafter, entry["subject"], placed)
        obj = _end(outline, drafter, entry["object"], placed)
        if subject is None or obj is None:
            _drop(out, entry["chunk"], sentence_index, "unknown_parent")
            continue
        action = entry.get("action")
        if entry["type"] == "rel" and (_side(subject), action, _side(obj)) in births:
            continue
        note = DraftNote(extractor="llm", confidence=entry["confidence"])
        if entry["type"] == "rel":
            planned = drafter.model_rel(subject, obj, action, note, entry.get("domainKey"))
        else:
            planned = drafter.model_spec(
                subject, obj, entry.get("rule"), note, entry.get("domainKey")
            )
        for draft in planned.drafts:
            if full():
                out.degraded = True
                _drop(out, entry["chunk"], sentence_index, "node_ceiling", draft.get("label"))
                break
            if draft["type"] == "relation":
                identity = (
                    draft.get("aId") or str(draft.get("aLabel", "")).lower(),
                    normalise_action(draft["action"]),
                    draft.get("bId") or str(draft.get("bLabel", "")).lower(),
                    "relation",
                )
                if identity in relations:
                    continue
                relations.add(identity)
            requires, depth = _placement(view, draft, drafted)
            if draft["type"] in ("concept", "spec"):
                if label_key(draft["label"]) in drafted:
                    continue
                drafted[label_key(draft["label"])] = (len(out.drafts), draft["label"], depth or 1)
            out.drafts.append(draft)
            out.notes.append(
                _note(
                    "section",
                    entry["confidence"],
                    entry.get("explanation"),
                    None,
                    depth,
                    requires,
                    sentence_index,
                    entry.get("span"),
                    origin_details,
                )
            )
    _order(out)
    return out


def _existing(outline: Outline, node: dict[str, Any]) -> Concept | None:
    """The live concept a node stands for: the one it reuses, or one of the company that now
    holds its label."""
    if node.get("conceptId"):
        concept = outline.view.concepts.get(uuid.UUID(node["conceptId"]))
        if concept is not None and concept.dying_at is None:
            return concept
    return outline.concept_by_label(node["label"])


def _parent_end(
    outline: Outline, node: dict[str, Any], placed: dict[int, End | None]
) -> End | None:
    if node.get("parentIndex") is not None:
        return placed.get(node["parentIndex"])
    parent_id = node.get("parentConceptId")
    concept = outline.view.concepts.get(uuid.UUID(parent_id)) if parent_id else None
    if concept is None or concept.dying_at is not None:
        return None
    return End(concept, concept.label, concept.label)


def _end(
    outline: Outline, drafter: Drafter, stored: dict[str, Any], placed: dict[int, End | None]
) -> End | None:
    if "node" in stored:
        return placed.get(int(stored["node"]))
    if "concept" in stored:
        concept = outline.view.concepts.get(uuid.UUID(stored["concept"]))
        if concept is None or concept.dying_at is not None:
            return None
        return End(concept, concept.label, concept.label)
    label = stored["label"]
    concept = drafter.resolve(label)
    if concept is not None:
        return End(concept, concept.label, concept.label)
    return End(None, label, label, cited_new=True)


def _placement(
    view: OntologyView, draft: dict[str, Any], drafted: dict[str, tuple[int, str, int]]
) -> tuple[list[int], int | None]:
    """The indexes of the earlier drafts a draft depends on, and its depth below the root."""
    requires: list[int] = []
    for key in ("parentLabel", "aLabel", "bLabel"):
        label = draft.get(key)
        if label and label_key(label) in drafted:
            requires.append(drafted[label_key(label)][0])
    if draft["type"] == "relation":
        return list(dict.fromkeys(requires))[:2], None
    if draft.get("parentId"):
        parent = view.concepts.get(uuid.UUID(draft["parentId"]))
        return requires, (len(view.ancestors_of(parent.id)) + 1) if parent else 1
    found = drafted.get(label_key(draft.get("parentLabel") or ""))
    return requires, (found[2] + 1) if found else 1


def _note(
    pass_name: str,
    confidence: float,
    explanation: str | None,
    role: str | None,
    depth: int | None,
    requires: list[int],
    sentence_index: int,
    span: list[int] | None,
    origin_details: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    note: dict[str, Any] = {
        "pass": pass_name,
        "confidence": confidence,
        "depth": depth,
        "requires": requires,
        "sentenceIndex": sentence_index,
        ORIGIN_DETAIL: origin_details[sentence_index],
    }
    if explanation:
        note["explanation"] = explanation[:MAX_EXPLANATION]
    if role:
        note["role"] = role
    if span:
        note["sourceSpan"] = {"start": span[0], "end": span[1]}
    return note


def _side(end: End) -> str:
    return str(end.concept.id) if end.concept is not None else end.label.lower()


def _drop(
    out: Mapped, chunk: int, sentence_index: int, reason: str, label: str | None = None
) -> None:
    if len(out.unresolved) >= MAX_UNRESOLVED:
        return
    item: dict[str, Any] = {"chunk": chunk, "sentenceIndex": sentence_index, "reason": reason}
    if label:
        item["label"] = label[:120]
    out.unresolved.append(item)


def _order(out: Mapped) -> None:
    """Concept and spec drafts first, relations last, keeping every `requires` index valid."""
    order = [i for i, d in enumerate(out.drafts) if d["type"] != "relation"]
    order += [i for i, d in enumerate(out.drafts) if d["type"] == "relation"]
    new_index = {old: new for new, old in enumerate(order)}
    out.drafts = [out.drafts[i] for i in order]
    notes = [out.notes[i] for i in order]
    for note in notes:
        note["requires"] = [new_index[r] for r in note["requires"]]
    out.notes = notes
