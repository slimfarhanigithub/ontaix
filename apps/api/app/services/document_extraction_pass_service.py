"""The two model passes of a whole-document extraction job, one chunk at a time: what the model
receives, and how its answer is checked, grounded and added to the job's outline.

Pass 1 returns outline nodes. A node attaches under a candidate concept or an outline node by
handle, under an earlier node of the same answer by key, or under a path of labels resolved
against the whole outline and the company's concepts; its label is grounded in its own cited
sentence and sliced from the document. A node whose label names an outline node or an existing
concept is that node or concept. Pass 2 returns intents against the frozen outline, their new
labels grounded the same way. An answer that fails a check is refused as a whole; a node or
intent that fails a rule is dropped with what depends on it and listed as unresolved.

The outline is stored as a list of entries: `node` entries in acceptance order, their handles
`o1`, `o2` and so on stable for the job, and the `intent` entries pass 2 accepted.
"""

from __future__ import annotations

import json
import logging
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.models.llm.document_extraction_answer import (
    HandleRef,
    KeyRef,
    NewLabelRef,
    OutlineAnswer,
    PathRef,
    SectionAnswer,
    SectionIntent,
)
from app.models.storage.base import NodeKind
from app.models.storage.concept import Concept
from app.services.extraction_event_service import NODE
from app.services.ontology_view_service import OntologyView
from app.services.teach_extraction_service import ground_in_sentence, quote_range
from app.utilities.action_text import has_refused_character, normalise_action
from app.utilities.teach_parser import singular

logger = logging.getLogger(__name__)

INTENT = "intent"
MAX_CANDIDATES = 200
MIN_CONFIDENCE = 0.4
MAX_ERRORS_SHOWN = 5
# Actions a `spec` intent may carry and still be a specialisation.
SPEC_ACTIONS = frozenset({"is a", "is a kind of", "is a type of", "is one of", "is kind of"})
DEFAULT_DOMAIN = "production"
REFUSED_ACTIONS = frozenset({"is a", "equivalent to"})
MAX_UNRESOLVED_LABEL = 120

# Where a node or an intent end sits: an outline node by index, or an existing concept.
Target = tuple[Literal["node"], int] | tuple[Literal["concept"], uuid.UUID]


@dataclass(frozen=True)
class Sentence:
    index: int
    text: str


@dataclass(frozen=True)
class Chunk:
    number: int
    sentences: list[Sentence]

    def text_of(self, sentence_index: int) -> str | None:
        return next((s.text for s in self.sentences if s.index == sentence_index), None)


@dataclass
class ChunkResult:
    """What one answer added: outline entries and unresolved items."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)


class InvalidAnswer(Exception):
    """The answer failed the schema or a check the schema cannot express."""


class _Dropped(Exception):
    def __init__(self, reason: str, label: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.label = label


class Outline:
    """The job's outline with the company's concepts, for handles, paths and label lookups."""

    def __init__(self, view: OntologyView, company_id: uuid.UUID, entries: list[dict[str, Any]]):
        self.view = view
        self.company_id = company_id
        root = view.root_of(company_id)
        assert root is not None
        self.root = root
        self.entries = entries
        self.nodes = [e for e in entries if e.get("kind") == NODE]
        self.concepts = [
            c for c in view.live_concepts() if c.company_id == company_id and c.dying_at is None
        ]

    def mark(self) -> tuple[int, int]:
        """A point to roll back to when reading an answer fails midway."""
        return len(self.nodes), len(self.entries)

    def rollback(self, mark: tuple[int, int]) -> None:
        del self.nodes[mark[0] :]
        del self.entries[mark[1] :]

    def add_node(self, node: dict[str, Any]) -> int:
        node["index"] = len(self.nodes)
        node["handle"] = f"o{len(self.nodes) + 1}"
        self.nodes.append(node)
        self.entries.append(node)
        return node["index"]

    def node_by_label(self, label: str) -> int | None:
        key = label_key(label)
        return next((n["index"] for n in self.nodes if label_key(n["label"]) == key), None)

    def node_for_concept(self, concept_id: uuid.UUID) -> int | None:
        wanted = str(concept_id)
        return next((n["index"] for n in self.nodes if n.get("conceptId") == wanted), None)

    def concept_by_label(self, label: str) -> Concept | None:
        key = label_key(label)
        return next((c for c in self.concepts if label_key(c.label) == key), None)

    def depth_of(self, target: Target) -> int:
        if target[0] == "node":
            return int(self.nodes[target[1]]["depth"])
        concept = self.view.concepts.get(target[1])
        return len(self.view.ancestors_of(concept.id)) if concept else 0

    def domain_of(self, target: Target) -> str:
        if target[0] == "node":
            return str(self.nodes[target[1]]["domainKey"])
        concept = self.view.concepts.get(target[1])
        return (self.view.domain_key(concept) if concept else None) or DEFAULT_DOMAIN

    def label_of(self, target: Target) -> str:
        if target[0] == "node":
            return str(self.nodes[target[1]]["label"])
        concept = self.view.concepts.get(target[1])
        return concept.label if concept else ""

    def children(self, target: Target) -> list[tuple[str, Target]]:
        """Labels and targets directly below a node or a concept."""
        out: list[tuple[str, Target]] = []
        if target[0] == "concept":
            out.extend(
                (c.label, ("concept", c.id))
                for c in self.concepts
                if c.parent_id == target[1] and c.kind is NodeKind.CONCEPT
            )
            out.extend(
                (n["label"], ("node", n["index"]))
                for n in self.nodes
                if n.get("parentConceptId") == str(target[1]) and n.get("parentIndex") is None
            )
        else:
            out.extend(
                (n["label"], ("node", n["index"]))
                for n in self.nodes
                if n.get("parentIndex") == target[1]
            )
        return out

    def resolve_path(self, path: list[str]) -> Target | None:
        """Walk the labels down from the company root, one normalised label per level."""
        current: Target = ("concept", self.root.id)
        for label in path:
            key = label_key(label)
            step = next((t for name, t in self.children(current) if label_key(name) == key), None)
            if step is None:
                return None
            current = self.canonical(step)
        return current

    def canonical(self, target: Target) -> Target:
        """A concept the outline reuses is addressed through its node."""
        if target[0] == "concept":
            index = self.node_for_concept(target[1])
            if index is not None:
                return ("node", index)
        return target


class Handles:
    """The handles one call sends: candidates `c0`..`c199` and outline nodes `oN`."""

    def __init__(self, candidates: list[Concept], sent_nodes: list[int]):
        self.candidates = candidates
        self.sent_nodes = set(sent_nodes)

    def target(self, handle: str, outline: Outline) -> Target:
        if handle.startswith("c"):
            index = int(handle[1:])
            if index >= len(self.candidates):
                raise InvalidAnswer("a cited candidate was not sent")
            return outline.canonical(("concept", self.candidates[index].id))
        index = int(handle[1:]) - 1
        if index not in self.sent_nodes:
            raise InvalidAnswer("a cited outline node was not sent")
        return ("node", index)


def select_handles(outline: Outline, chunk: Chunk, limit_nodes: int) -> Handles:
    """The candidates and the outline nodes sent with one chunk."""
    text = " ".join(s.text for s in chunk.sentences).lower()
    nodes = _outline_context(outline, text, limit_nodes)
    chosen: list[Concept] = []
    seen: set[uuid.UUID] = set()

    def take(concept: Concept | None) -> None:
        if concept is None or concept.id in seen or len(chosen) >= MAX_CANDIDATES:
            return
        seen.add(concept.id)
        chosen.append(concept)

    take(outline.root)
    for index in nodes:
        node = outline.nodes[index]
        for key in ("conceptId", "parentConceptId"):
            if node.get(key):
                take(outline.view.concepts.get(uuid.UUID(node[key])))
    for concept in outline.concepts:
        if concept.kind is NodeKind.CONCEPT and _mentioned(concept.label, text):
            take(concept)
    for concept in sorted(outline.concepts, key=lambda c: (c.born_at, str(c.id)), reverse=True):
        take(concept)
    return Handles(chosen, nodes)


def context(
    outline: Outline,
    handles: Handles,
    chunk: Chunk,
    chunks: int,
    company_name: str,
    pass_name: Literal["outline", "section"],
) -> str:
    """The user message: the chunk and the handles as JSON data, no id of any kind."""
    handle_of = {c.id: f"c{i}" for i, c in enumerate(handles.candidates)}
    view = outline.view

    def parent_handle(node: dict[str, Any]) -> str | None:
        if node.get("parentIndex") is not None:
            return f"o{node['parentIndex'] + 1}"
        parent = node.get("parentConceptId")
        return handle_of.get(uuid.UUID(parent)) if parent else None

    data: dict[str, Any] = {
        "pass": pass_name,
        "company": company_name,
        "chunk": {"number": chunk.number + 1, "of": chunks},
        "sentences": [{"index": s.index, "text": s.text} for s in chunk.sentences],
        "outline": [
            {
                "handle": outline.nodes[i]["handle"],
                "parent": parent_handle(outline.nodes[i]),
                "label": outline.nodes[i]["label"],
            }
            for i in sorted(handles.sent_nodes)
        ],
        "candidates": [
            {
                "handle": handle_of[c.id],
                "label": c.label,
                "parent": handle_of.get(c.parent_id) if c.parent_id else None,
                "domain": view.domain_key(c),
            }
            for c in handles.candidates
        ],
        "domainTemplates": [
            {"key": key, "name": t.name}
            for key, t in sorted(view.templates.items(), key=lambda kv: kv[1].position)
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def read_outline_answer(raw: str, outline: Outline, handles: Handles, chunk: Chunk) -> ChunkResult:
    """Checks a pass 1 answer and adds its accepted nodes to `outline`."""
    try:
        answer = OutlineAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise InvalidAnswer(_schema_errors(exc)) from None
    keys: set[str] = set()
    for node in answer.nodes:
        if node.key in keys:
            raise InvalidAnswer("a key repeats")
        if isinstance(node.parent, KeyRef) and node.parent.key not in keys:
            raise InvalidAnswer("a parent key is not defined earlier in the answer")
        if isinstance(node.parent, HandleRef):
            handles.target(node.parent.handle, outline)
        keys.add(node.key)
        _check_action(node.action)
        _check_sentence(chunk, node.sentence_index)
        _check_texts(node.label, node.span, *_path_of(node.parent))
        if isinstance(node.parent, PathRef) and label_key(node.parent.path[-1]) == label_key(
            node.label
        ):
            raise InvalidAnswer("a node joins a concept to itself")

    result = ChunkResult()
    by_key: dict[str, Target | _Dropped] = {}
    for node in answer.nodes:
        try:
            parent = _parent_target(node.parent, by_key, outline, handles)
            if node.confidence < MIN_CONFIDENCE:
                raise _Dropped("low_confidence")
            sentence = chunk.text_of(node.sentence_index)
            assert sentence is not None
            grounded = ground_in_sentence(node.label, sentence)
            if grounded is None:
                raise _Dropped("ungrounded_label")
            label, start, end = grounded
            by_key[node.key] = _accept_node(
                outline,
                result,
                parent,
                label,
                (start, end),
                node.action,
                node.role,
                node.domain_key,
                node.confidence,
                node.sentence_index,
                chunk.number,
            )
        except _Dropped as dropped:
            by_key[node.key] = dropped
            result.unresolved.append(
                _unresolved(chunk.number, node.sentence_index, dropped.reason, dropped.label)
            )
    return result


def read_section_answer(raw: str, outline: Outline, handles: Handles, chunk: Chunk) -> ChunkResult:
    """Checks a pass 2 answer and returns its accepted intents as outline entries."""
    try:
        answer = SectionAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise InvalidAnswer(_schema_errors(exc)) from None
    for intent in answer.intents:
        for ref in (intent.subject, intent.object):
            if isinstance(ref, KeyRef):
                raise InvalidAnswer("a section answer defines no keys")
            if isinstance(ref, HandleRef):
                handles.target(ref.handle, outline)
            _check_texts(*_path_of(ref), ref.new_label if isinstance(ref, NewLabelRef) else None)
        if intent.subject == intent.object:
            raise InvalidAnswer("an intent joins a concept to itself")
        _check_texts(intent.action, intent.span, intent.rule, intent.explanation)
        _check_sentence(chunk, intent.sentence_index)
    for item in answer.unresolved:
        _check_sentence(chunk, item.sentence_index)

    result = ChunkResult()
    for intent in answer.intents:
        sentence = chunk.text_of(intent.sentence_index)
        assert sentence is not None
        try:
            kind, action, rule = _read_kind(intent)
            if intent.confidence < MIN_CONFIDENCE:
                raise _Dropped("low_confidence")
            subject = _intent_end(intent.subject, outline, handles, sentence)
            obj = _intent_end(intent.object, outline, handles, sentence)
            if subject == obj:
                raise _Dropped("not_understood")
        except _Dropped as dropped:
            result.unresolved.append(
                _unresolved(chunk.number, intent.sentence_index, dropped.reason, dropped.label)
            )
            continue
        span = quote_range(sentence, intent.span)
        entry = {
            "kind": INTENT,
            "type": kind,
            "subject": subject,
            "object": obj,
            "action": action,
            "rule": rule,
            "domainKey": intent.domain_key,
            "confidence": intent.confidence,
            "explanation": intent.explanation,
            "sentenceIndex": intent.sentence_index,
            "span": list(span) if span else None,
            "chunk": chunk.number,
        }
        result.entries.append(entry)
    for item in answer.unresolved:
        result.unresolved.append(_unresolved(chunk.number, item.sentence_index, item.reason))
    return result


def _read_kind(intent: SectionIntent) -> tuple[str, str | None, str | None]:
    """The intent's kind, normalised action and rule, read by its fields when they disagree
    with its kind rather than refusing the chunk: an action that says `is a` makes a spec
    without one, any other action makes a `rel` with that action and no rule, a `rel` without
    an action and an `equivalent to` action are not understood."""
    action = normalise_action(intent.action) if intent.action else None
    if action in SPEC_ACTIONS:
        return "spec", None, intent.rule
    if action in REFUSED_ACTIONS or (intent.kind == "rel" and action is None):
        raise _Dropped("not_understood")
    if action is not None:
        return "rel", action, None
    return "spec", None, intent.rule


def _schema_errors(exc: ValidationError) -> str:
    """The count of schema errors with the field and kind of the first few, never a value the
    model wrote, so a refusal names what the answer got wrong."""
    shown = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
        for error in exc.errors()[:MAX_ERRORS_SHOWN]
    ]
    return f"{exc.error_count()} schema errors ({'; '.join(shown)})"


def label_key(label: str) -> str:
    """Labels compare case-insensitively, singular or plural."""
    return singular(unicodedata.normalize("NFKC", label).strip().lower())


def unresolved_chunk(chunk: Chunk, reason: str) -> dict[str, Any]:
    return {"chunk": chunk.number, "reason": reason}


def _accept_node(
    outline: Outline,
    result: ChunkResult,
    parent: Target,
    label: str,
    span: tuple[int, int],
    action: str,
    role: str,
    domain_key: str | None,
    confidence: float,
    sentence_index: int,
    chunk_number: int,
) -> Target:
    """The node a grounded label becomes: an outline node or concept with that label, or a new
    node under `parent`."""
    same = outline.node_by_label(label)
    if same is not None:
        return ("node", same)
    concept = outline.concept_by_label(label)
    if concept is not None:
        existing = outline.node_for_concept(concept.id)
        if existing is not None:
            return ("node", existing)
        node = _node_for_concept(outline, concept, role, sentence_index, chunk_number)
    else:
        if parent[0] == "concept" and parent[1] == outline.root.id:
            domain = domain_key or DEFAULT_DOMAIN
        else:
            domain = domain_key or outline.domain_of(parent)
        node = {
            "kind": NODE,
            "parentIndex": parent[1] if parent[0] == "node" else None,
            "parentConceptId": str(parent[1]) if parent[0] == "concept" else None,
            "conceptId": None,
            "label": label,
            "role": role,
            "depth": outline.depth_of(parent) + 1,
            "sentenceIndex": sentence_index,
            "action": normalise_action(action),
            "domainKey": domain,
            "confidence": confidence,
            "span": [span[0], span[1]],
            "chunk": chunk_number,
        }
    index = outline.add_node(node)
    result.entries.append(node)
    return ("node", index)


def _node_for_concept(
    outline: Outline, concept: Concept, role: str, sentence_index: int, chunk_number: int
) -> dict[str, Any]:
    """An outline node standing for an existing concept, where the concept already sits."""
    parent_id = concept.parent_id
    return {
        "kind": NODE,
        "parentIndex": None,
        "parentConceptId": str(parent_id) if parent_id else None,
        "conceptId": str(concept.id),
        "label": concept.label,
        "role": role,
        "depth": max(1, len(outline.view.ancestors_of(concept.id))),
        "sentenceIndex": sentence_index,
        "action": concept.birth_action or "",
        "domainKey": outline.view.domain_key(concept) or DEFAULT_DOMAIN,
        "confidence": 1.0,
        "span": None,
        "chunk": chunk_number,
    }


def _parent_target(
    ref: HandleRef | KeyRef | PathRef,
    by_key: dict[str, Target | _Dropped],
    outline: Outline,
    handles: Handles,
) -> Target:
    if isinstance(ref, HandleRef):
        return handles.target(ref.handle, outline)
    if isinstance(ref, KeyRef):
        found = by_key[ref.key]
        if isinstance(found, _Dropped):
            raise _Dropped(found.reason)
        return found
    target = outline.resolve_path(list(ref.path))
    if target is None:
        raise _Dropped("unknown_parent")
    return target


def _intent_end(ref: Any, outline: Outline, handles: Handles, sentence: str) -> dict[str, Any]:
    """A stored intent end: `{"node": i}`, `{"concept": id}` or a new grounded label."""
    if isinstance(ref, HandleRef):
        return _stored(handles.target(ref.handle, outline))
    if isinstance(ref, PathRef):
        target = outline.resolve_path(list(ref.path))
        if target is None:
            raise _Dropped("unknown_parent")
        return _stored(target)
    assert isinstance(ref, NewLabelRef)
    grounded = ground_in_sentence(ref.new_label, sentence)
    if grounded is None:
        raise _Dropped("ungrounded_label")
    label, start, end = grounded
    node = outline.node_by_label(label)
    if node is not None:
        return {"node": node}
    concept = outline.concept_by_label(label)
    if concept is not None:
        return _stored(outline.canonical(("concept", concept.id)))
    return {"label": label, "span": [start, end]}


def _stored(target: Target) -> dict[str, Any]:
    return {"node": target[1]} if target[0] == "node" else {"concept": str(target[1])}


def _outline_context(outline: Outline, text: str, limit: int) -> list[int]:
    """Every node while the outline is small; past `limit`, the nodes the chunk names with
    their ancestors, then the upper levels breadth-first, then the newest."""
    nodes = outline.nodes
    if len(nodes) <= limit:
        return [n["index"] for n in nodes]
    chosen: list[int] = []
    seen: set[int] = set()

    def take(index: int) -> None:
        if index not in seen and len(chosen) < limit:
            seen.add(index)
            chosen.append(index)

    for node in nodes:
        if _mentioned(node["label"], text):
            chain: list[int] = []
            current: int | None = node["index"]
            while current is not None:
                chain.append(current)
                current = nodes[current].get("parentIndex")
            for index in reversed(chain):
                take(index)
    queue = deque(sorted(nodes, key=lambda n: (n["depth"], n["index"])))
    while queue and len(chosen) < limit:
        take(queue.popleft()["index"])
    for node in reversed(nodes):
        take(node["index"])
    return chosen


def _mentioned(label: str, text: str) -> bool:
    lower = label.lower()
    return lower in text or singular(lower) in text


def _check_action(action: str) -> None:
    normal = normalise_action(action)
    if not normal or normal in REFUSED_ACTIONS:
        raise InvalidAnswer("an action is is a or equivalent to")


def _check_sentence(chunk: Chunk, sentence_index: int) -> None:
    if chunk.text_of(sentence_index) is None:
        raise InvalidAnswer("a sentenceIndex lies outside the chunk")


def _check_texts(*texts: str | None) -> None:
    for text in texts:
        if text is not None and has_refused_character(text):
            raise InvalidAnswer("a text holds a refused character")


def _path_of(ref: Any) -> list[str]:
    return list(ref.path) if isinstance(ref, PathRef) else []


def _unresolved(
    chunk_number: int, sentence_index: int, reason: str, label: str | None = None
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "chunk": chunk_number,
        "sentenceIndex": sentence_index,
        "reason": reason,
    }
    if label:
        item["label"] = label[:MAX_UNRESOLVED_LABEL]
    return item
