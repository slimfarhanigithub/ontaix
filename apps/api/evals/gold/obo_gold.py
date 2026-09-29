"""An OBO ontology as a gold tree, read with obonet.

- `is_a` gives the tree; a term keeps every `is_a` parent. A term with no `is_a` parent inside
  the file hangs off the company root; a term whose name is the company's name is the root
  itself. The action of an `is_a` edge is the term's `property_value: birth_action "..."`, else
  "is a", followed by its `accepted_action` values.
- `relationship: <relation> <term>` gives relations; the verb is the relation's `[Typedef]`
  `birth_action`, else its name, else its identifier split into lower-case words, followed by
  the typedef's `accepted_action` values; its `inverse_action` values are the inverse actions.
- `name` is the label, else the identifier; `synonym`s are aliases.
- Obsolete terms are skipped and listed; every other tag of a term (and every other
  `property_value`) is reported by name.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import obonet

from evals.gold.common import (
    Actions,
    action_annotation,
    clean,
    finish,
    key,
    relation,
    verb_from_name,
)
from evals.gold.gold_tree import GoldTree
from evals.teach_case import ExpectedConcept, ExpectedRelation

_SYNONYM = re.compile(r'^"((?:[^"\\]|\\.)*)"')
_PROPERTY_VALUE = re.compile(r'^(\S+)\s+"((?:[^"\\]|\\.)*)"')
# Term tags the import reads; obonet also turns `is_a` and `relationship` into edges.
_READ_TAGS = frozenset({"name", "synonym", "is_obsolete", "is_a", "relationship", "property_value"})


def load_obo(path: Path, company: str) -> GoldTree:
    graph = obonet.read_obo(path, ignore_obsolete=False)
    ignored: Counter[str] = Counter()
    verbs: dict[str, tuple[list[str], list[str]]] = {}
    for t in graph.graph.get("typedefs", []):
        found = _actions(t.get("property_value", []), ignored)
        default = clean(t["name"]).lower() if "name" in t else verb_from_name(t["id"])
        verbs[t["id"]] = (found.listed(default), found.inverse)
    obsolete = {n for n, d in graph.nodes(data=True) if d.get("is_obsolete") == "true"}
    terms = {n for n, d in graph.nodes(data=True) if d and n not in obsolete}

    def label_of(term: str) -> str:
        return clean(graph.nodes[term].get("name", term))

    roots = {t for t in terms if key(label_of(t)) == key(company)}

    def node_label(term: str) -> str:
        return company if term in roots else label_of(term)

    parents: dict[str, list[str]] = {t: [] for t in terms - roots}
    relations: list[ExpectedRelation] = []
    external: Counter[str] = Counter()
    for child, target, rel in graph.edges(keys=True):
        if child not in parents:
            continue
        if target not in terms:
            external[rel] += 1
            continue
        if rel == "is_a":
            parents[child].append(node_label(target))
        else:
            actions, inverse = verbs.get(rel) or ([verb_from_name(rel.rsplit(":", 1)[-1])], [])
            relations.append(relation(label_of(child), node_label(target), actions, inverse))

    term_actions = {t: _actions(graph.nodes[t].get("property_value", []), ignored) for t in terms}
    for t in terms:
        ignored.update(tag for tag in graph.nodes[t] if tag not in _READ_TAGS)

    concepts = [
        ExpectedConcept(
            label=label_of(t),
            parent=sorted(set(parents[t])) or [company],
            action=term_actions[t].listed("is a"),
            aliases=_synonyms(graph.nodes[t].get("synonym", [])),
        )
        for t in sorted(parents)
    ]
    report: dict[str, object] = {
        "terms": len(terms - roots),
        "typedefs": sorted(actions[0] for actions, _ in verbs.values()),
        "obsoleteTerms": sorted(graph.nodes[n].get("name", n) for n in obsolete),
        "edgesToExternalTerms": dict(sorted(external.items())),
        "ignoredAxioms": dict(sorted(ignored.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    return finish(concepts, relations, [], report, company, "obo")


def _actions(values: list[str], ignored: Counter[str]) -> Actions:
    """The verb annotations among `property_value` lines; others are counted as ignored."""
    found = Actions()
    for value in values:
        match = _PROPERTY_VALUE.match(value.strip())
        kind = action_annotation(match.group(1)) if match else None
        if match and kind is not None:
            found.add(kind, match.group(2).replace('\\"', '"'))
        else:
            ignored[f"property_value {value.strip().split(' ', 1)[0]}"] += 1
    return found


def _synonyms(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        match = _SYNONYM.match(value.strip())
        if match:
            out.append(clean(match.group(1).replace('\\"', '"')))
    return out
