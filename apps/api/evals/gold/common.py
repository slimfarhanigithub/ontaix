"""Helpers shared by the gold importers: names split into words, labels and verbs cleaned up,
concepts merged by label, relations de-duplicated, and the finished `GoldTree` with its depth."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from evals.gold.gold_tree import GoldTree
from evals.teach_case import Expected, ExpectedConcept, ExpectedRelation

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[_\-\s]+")
# A trailing cardinality annotation such as " (0..1)", " (1..*)" or " (0..n)".
_CARDINALITY = re.compile(r"\s*\(\s*[0-9*n]+\s*\.\.\s*[0-9*n]+\s*\)\s*$", re.IGNORECASE)
_ACTION_ANNOTATIONS = {
    "birthaction": "birth",
    "acceptedaction": "accepted",
    "inverseaction": "inverse",
}


def split_name(name: str) -> list[str]:
    """`OrderToCash`, `order_to_cash` and `order-to-cash` as words."""
    return [w for part in _SEPARATORS.split(name) for w in _CAMEL.split(part) if w]


def humanise(name: str) -> str:
    """A local name or identifier as a label: words, first letter upper-case."""
    text = " ".join(split_name(name))
    return text[:1].upper() + text[1:] if text else name


def verb_from_name(name: str) -> str:
    """A property or relation identifier as a verb: lower-case words."""
    return clean(" ".join(w.lower() for w in split_name(name)))


def clean(text: str) -> str:
    """A label or verb without surrounding space, doubled spaces or a cardinality suffix."""
    return " ".join(_CARDINALITY.sub("", text.strip()).split())


def key(label: str) -> str:
    return " ".join(label.casefold().split())


def relation(
    source: str, target: str, actions: list[str], inverse: list[str] | None = None
) -> ExpectedRelation:
    """A relation read from `source` to `target`; the first action is the verb, the others are
    also accepted, and `inverse` lists the actions accepted when read from target to source."""
    return ExpectedRelation.model_validate(
        {
            "from": source,
            "to": target,
            "action": _ordered(actions),
            "inverse": _ordered(inverse or []),
        }
    )


@dataclass
class Actions:
    """The verb annotations of a class, concept, term or property: the birth action (the verb
    it is drafted with), other accepted actions, and inverse actions (for a property)."""

    birth: list[str] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)
    inverse: list[str] = field(default_factory=list)

    def add(self, kind: str, value: str) -> None:
        getattr(self, kind).append(clean(value).lower())

    def listed(self, default: str) -> list[str]:
        """The birth action (else `default`) first, then the accepted actions."""
        return _ordered([*(self.birth or [default]), *sorted(self.accepted)])


def action_annotation(name: str) -> str | None:
    """ "birth", "accepted" or "inverse" when a local name (`birthAction`, `birth_action`,
    `acceptedAction`, `inverse_action`, ...) is a verb annotation; None otherwise."""
    return _ACTION_ANNOTATIONS.get(re.sub(r"[^a-z]", "", name.lower()))


def merge_by_label(concepts: list[ExpectedConcept]) -> list[ExpectedConcept]:
    """Concepts that share a label are one expected concept with every parent, action and alias
    of each, in first-seen order."""
    merged: dict[str, ExpectedConcept] = {}
    for c in concepts:
        k = key(c.label)
        if k not in merged:
            merged[k] = c
            continue
        seen = merged[k]
        merged[k] = seen.model_copy(
            update={
                "parent": _ordered([*seen.parent, *c.parent]),
                "action": _ordered([*seen.action, *c.action]),
                "aliases": _ordered([*seen.aliases, *c.aliases]),
            }
        )
    return list(merged.values())


def unique_relations(relations: list[ExpectedRelation]) -> list[ExpectedRelation]:
    seen: set[tuple[str, str, str]] = set()
    out: list[ExpectedRelation] = []
    for r in relations:
        k = (key(r.source), key(r.target), r.action[0])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def finish(
    concepts: list[ExpectedConcept],
    relations: list[ExpectedRelation],
    optional: list[str],
    report: dict[str, object],
    company: str,
    fmt: str,
) -> GoldTree:
    """The gold tree: concepts merged by label (the company itself is the root, not a concept),
    no concept its own parent, optional labels that are not concepts, and a report that starts
    with the format, the counts and the depth."""
    company_key = key(company)
    kept: list[ExpectedConcept] = []
    for c in merge_by_label(concepts):
        if key(c.label) == company_key:
            continue
        parents = _ordered([p for p in c.parent if key(p) != key(c.label)]) or [company]
        aliases = [a for a in c.aliases if key(a) != key(c.label)]
        kept.append(c.model_copy(update={"parent": parents, "aliases": _ordered(aliases)}))
    concept_keys = {key(c.label) for c in kept}
    extra = sorted({o for o in optional if key(o) not in concept_keys | {company_key}})
    rels = unique_relations(relations)
    depth, unreachable = depth_of(kept, company)
    head: dict[str, object] = {
        "format": fmt,
        "concepts": len(kept),
        "relations": len(rels),
        "optional": len(extra),
        "maxDepth": depth,
        "unreachable": unreachable,
    }
    return GoldTree(
        expected=Expected(concepts=kept, relations=rels),
        optional=extra,
        report={**head, **{k: v for k, v in report.items() if k not in head}},
    )


def depth_of(concepts: list[ExpectedConcept], company: str) -> tuple[int, list[str]]:
    """The deepest level (shortest distance from the company root) and the labels of concepts
    that no chain of parents joins to the root."""
    children: dict[str, list[str]] = {}
    for c in concepts:
        for p in c.parent:
            children.setdefault(key(p), []).append(key(c.label))
    level = {key(company): 0}
    queue = deque([key(company)])
    while queue:
        node = queue.popleft()
        for child in children.get(node, []):
            if child not in level:
                level[child] = level[node] + 1
                queue.append(child)
    unreachable = sorted(c.label for c in concepts if key(c.label) not in level)
    return max(level.values()), unreachable


def _ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and key(v) not in seen:
            seen.add(key(v))
            out.append(v)
    return out
