"""A plain JSON tree or graph as a gold tree. JSON-LD (a document with `@context` or `@graph`)
is RDF and is read by the RDF importer instead.

Two shapes:

- Nested: a node is an object with `label` (or `name`, `title`), optional `children`, optional
  `verb` (or `action`, `actions`; a string or a list, the first the birth action), optional
  `aliases` and optional `alsoUnder` (labels of further parents); the document is one node or a
  list of them, at any depth. Top-level nodes hang off the company root, and a top-level node
  whose label is the company's name is the root itself. The verb defaults to "has". A
  `relations` array on the top object lists relations: `from`/`source`, `to`/`target`,
  `actions` (or `action`, `verb`; a string or a list) and optional `inverse`.
- Graph: `nodes` (each with `id` and `label`/`name`) and `edges` (or `links`), each with
  `source`/`from`, `target`/`to` and a `label`/`verb`/`type`/`relation`. An edge whose type is
  a subclass or broader link (`is_a`, `subClassOf`, `parent`, `child_of`, `broader`) makes the
  target the source's parent; `narrower`, `child`, `has_child` make the source the target's
  parent. Every other edge is a relation, its verb the type split into lower-case words. Nodes
  with no parent hang off the company root.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evals.gold.common import clean, finish, humanise, key, relation, verb_from_name
from evals.gold.gold_tree import GoldTree
from evals.teach_case import ExpectedConcept, ExpectedRelation

_LABEL_KEYS = ("label", "name", "title")
_VERB_KEYS = ("verb", "action", "actions")
_EDGE_TYPE_KEYS = ("type", "label", "verb", "relation", "predicate")
# Edge types (keyed as `_type_key` returns them) read as "target is the source's parent".
_CHILD_TO_PARENT = {"is a": "is a", "isa": "is a", "subclassof": "is a", "sub class of": "is a"}
_CHILD_TO_PARENT_HAS = frozenset({"parent", "child of", "broader"})
_PARENT_TO_CHILD = frozenset({"narrower", "child", "has child"})


def is_json_ld(data: object) -> bool:
    items = data if isinstance(data, list) else [data]
    return any(
        isinstance(item, dict) and ("@context" in item or "@graph" in item or "@id" in item)
        for item in items
    )


def load_json(path: Path, company: str) -> GoldTree:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if is_json_ld(data):
        raise ValueError(f"{path.name}: JSON-LD is read by the RDF importer")
    if isinstance(data, dict) and "nodes" in data and ("edges" in data or "links" in data):
        return _graph(data, company)
    nodes = data if isinstance(data, list) else [data]
    concepts: list[ExpectedConcept] = []
    skipped: Counter[str] = Counter()
    for node in nodes:
        _nested(node, company, company, concepts, skipped, top=True)
    relations: list[ExpectedRelation] = []
    raw_relations = data.get("relations", []) if isinstance(data, dict) else []
    for item in raw_relations if isinstance(raw_relations, list) else []:
        read = _relation(item) if isinstance(item, dict) else None
        if read is None:
            skipped["relation without from, to or action"] += 1
        else:
            relations.append(read)
    report: dict[str, object] = {"nodesRead": len(concepts), "nodesSkipped": dict(skipped)}
    return finish(concepts, relations, [], report, company, "json-nested")


def _relation(item: dict) -> ExpectedRelation | None:
    source = _text(item.get("from", item.get("source")))
    target = _text(item.get("to", item.get("target")))
    actions = _listed(next((item[k] for k in ("actions", "action", "verb") if k in item), None))
    if not source or not target or not actions:
        return None
    inverse = [a.lower() for a in _listed(item.get("inverse"))]
    return relation(source, target, [a.lower() for a in actions], inverse)


def _text(value: object) -> str:
    return clean(value) if isinstance(value, str) else ""


def _nested(
    node: object,
    parent: str,
    company: str,
    out: list[ExpectedConcept],
    skipped: Counter[str],
    top: bool = False,
) -> None:
    if not isinstance(node, dict):
        skipped["not an object"] += 1
        return
    label = _label(node)
    children = node.get("children") or []
    if not label:
        skipped["no label"] += 1
        return
    if top and key(label) == key(company):
        this = company
    else:
        verbs = _listed(next((node[k] for k in _VERB_KEYS if k in node), None))
        out.append(
            ExpectedConcept(
                label=label,
                parent=[parent, *_listed(node.get("alsoUnder"))],
                action=[v.lower() for v in verbs] or ["has"],
                aliases=_listed(node.get("aliases")),
            )
        )
        this = label
    for child in children if isinstance(children, list) else []:
        _nested(child, this, company, out, skipped)


def _graph(data: dict, company: str) -> GoldTree:
    labels: dict[str, str] = {}
    for node in data["nodes"]:
        if isinstance(node, dict) and node.get("id") is not None:
            labels[str(node["id"])] = _label(node) or humanise(str(node["id"]))
    parents: dict[str, list[str]] = {n: [] for n in labels}
    actions: dict[str, list[str]] = {n: [] for n in labels}
    relations: list[ExpectedRelation] = []
    skipped: Counter[str] = Counter()
    for edge in data.get("edges") or data.get("links") or []:
        source = str(edge.get("source", edge.get("from", "")))
        target = str(edge.get("target", edge.get("to", "")))
        if source not in labels or target not in labels:
            skipped["unknown node"] += 1
            continue
        raw = next((str(edge[k]) for k in _EDGE_TYPE_KEYS if edge.get(k)), "")
        kind = _type_key(raw)
        if kind in _CHILD_TO_PARENT or kind in _CHILD_TO_PARENT_HAS:
            parents[source].append(target)
            actions[source].append(_CHILD_TO_PARENT.get(kind, "has"))
        elif kind in _PARENT_TO_CHILD:
            parents[target].append(source)
            actions[target].append("has")
        elif raw:
            relations.append(relation(labels[source], labels[target], [verb_from_name(raw)]))
        else:
            skipped["no type"] += 1
    roots = {n for n, label in labels.items() if key(label) == key(company)}

    def node_label(node: str) -> str:
        return company if node in roots else labels[node]

    concepts = [
        ExpectedConcept(
            label=labels[n],
            parent=sorted({node_label(p) for p in parents[n]}) or [company],
            action=sorted(set(actions[n])) or ["has"],
        )
        for n in labels
        if n not in roots
    ]
    report: dict[str, object] = {
        "nodesRead": len(labels),
        "edgesSkipped": dict(skipped),
    }
    return finish(concepts, relations, [], report, company, "json-graph")


def _type_key(raw: str) -> str:
    return verb_from_name(raw.rsplit(":", 1)[-1].rsplit("#", 1)[-1]).replace("-", " ")


def _label(node: dict) -> str:
    for k in _LABEL_KEYS:
        if isinstance(node.get(k), str) and node[k].strip():
            return clean(node[k])
    return ""


def _listed(value: object) -> list[str]:
    if isinstance(value, str):
        return [clean(value)] if value.strip() else []
    if isinstance(value, list):
        return [clean(v) for v in value if isinstance(v, str) and v.strip()]
    return []
