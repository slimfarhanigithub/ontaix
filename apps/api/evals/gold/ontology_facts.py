"""The facts an OWL ontology contributes to a gold tree, whatever its serialisation, and the
tree built from them.

- Named superclasses give the tree. A class with several keeps them all (the scorer accepts
  any). A class with none (or only `owl:Thing`) hangs off the company root; a class whose label
  is the company's name is the root itself. The action of a subclass edge is "is a".
- Object properties give relations: domain x range pairs, restrictions on a class (the filler
  class, or the individual of a `hasValue`), and assertions between individuals. The verb is the
  property's label, else its local name split from camelCase or snake_case, lower-case.
- A verb annotation (`birthAction`, `acceptedAction`, `inverseAction` in any namespace) on a
  class gives its actions (birth action first) and on a property the relation's actions and
  inverse actions; `skos:altLabel`s of a class are aliases.
- Labels are `rdfs:label` (English first, else the first), else the local name humanised; a
  trailing cardinality such as " (0..1)" is dropped from labels and verbs.
- Named individuals are optional leaves.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from evals.gold.common import Actions, clean, finish, humanise, key, relation, verb_from_name
from evals.gold.gold_tree import GoldTree
from evals.teach_case import ExpectedConcept, ExpectedRelation

OWL_THING = "http://www.w3.org/2002/07/owl#Thing"

# A label as read: its text and its language tag.
Label = tuple[str, str | None]


@dataclass
class OntologyFacts:
    """Entities are keyed by IRI."""

    labels: dict[str, list[Label]] = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)
    object_properties: set[str] = field(default_factory=set)
    datatype_properties: set[str] = field(default_factory=set)
    individuals: set[str] = field(default_factory=set)
    superclasses: dict[str, set[str]] = field(default_factory=dict)
    domains: dict[str, set[str]] = field(default_factory=dict)
    ranges: dict[str, set[str]] = field(default_factory=dict)
    # (owner class, object property, filler class or individual)
    restrictions: list[tuple[str, str, str]] = field(default_factory=list)
    # (individual, object property, individual)
    assertions: list[tuple[str, str, str]] = field(default_factory=list)
    # (owner class, property) of restrictions whose filler is a datatype or a data range.
    datatype_restrictions: list[tuple[str, str]] = field(default_factory=list)
    # Verb annotations (birth, accepted, inverse actions) of classes and properties.
    actions: dict[str, Actions] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    ignored: Counter[str] = field(default_factory=Counter)

    def label_of(self, iri: str) -> str:
        chosen = pick_label(self.labels.get(iri, []))
        return clean(chosen) if chosen is not None else humanise(local_name(iri))

    def verb_of(self, prop: str) -> str:
        chosen = pick_label(self.labels.get(prop, []))
        return clean(chosen).lower() if chosen is not None else verb_from_name(local_name(prop))

    def annotate(self, iri: str, kind: str, value: str) -> None:
        self.actions.setdefault(iri, Actions()).add(kind, value)

    def relation_actions(self, prop: str) -> tuple[list[str], list[str]]:
        """A property's actions (its birth action, else its verb, then the accepted ones) and
        its inverse actions."""
        found = self.actions.get(prop, Actions())
        return found.listed(self.verb_of(prop)), found.inverse


def build_tree(facts: OntologyFacts, company: str, fmt: str) -> GoldTree:
    classes = facts.classes - {OWL_THING}
    individuals = facts.individuals - classes - facts.object_properties
    roots = {c for c in classes if key(facts.label_of(c)) == key(company)}

    def node_label(iri: str) -> str:
        return company if iri in roots else facts.label_of(iri)

    concepts: list[ExpectedConcept] = []
    for c in sorted(classes - roots):
        named = sorted(node_label(s) for s in facts.superclasses.get(c, set()) if s in classes)
        concepts.append(
            ExpectedConcept(
                label=facts.label_of(c),
                parent=named or [company],
                action=facts.actions.get(c, Actions()).listed("is a"),
                aliases=facts.aliases.get(c, []),
            )
        )

    relations: list[ExpectedRelation] = []
    for owner, prop, filler in facts.restrictions:
        if owner in classes and (filler in classes or filler in individuals):
            relations.append(
                relation(node_label(owner), node_label(filler), *facts.relation_actions(prop))
            )
    for prop in sorted(facts.object_properties):
        actions, inverse = facts.relation_actions(prop)
        for d in sorted(facts.domains.get(prop, set()) & classes):
            for r in sorted(facts.ranges.get(prop, set()) & classes):
                relations.append(relation(node_label(d), node_label(r), actions, inverse))
    for s, prop, o in facts.assertions:
        if s in individuals and o in individuals:
            relations.append(
                relation(facts.label_of(s), facts.label_of(o), *facts.relation_actions(prop))
            )

    report: dict[str, object] = {
        "classes": len(classes - roots),
        "rootClasses": sorted(roots),
        "objectProperties": len(facts.object_properties),
        "individuals": len(individuals),
        "ignoredAxioms": dict(sorted(facts.ignored.items(), key=lambda kv: (-kv[1], kv[0]))),
        "datatypeProperties": sorted(facts.label_of(p) for p in facts.datatype_properties),
        "datatypeRestrictions": sorted(
            f"{facts.label_of(o)} . {facts.label_of(p)}" for o, p in facts.datatype_restrictions
        ),
    }
    optional = [facts.label_of(i) for i in individuals]
    return finish(concepts, relations, optional, report, company, fmt)


def pick_label(labels: list[Label]) -> str | None:
    """English first, else the first in text order; None when there is no label."""
    english = sorted(t for t, lang in labels if (lang or "").lower().startswith("en"))
    chosen = english or sorted(t for t, lang in labels if not lang) or sorted(t for t, _ in labels)
    return chosen[0] if chosen else None


def local_name(iri: str) -> str:
    text = iri
    for sep in ("#", "/", ":"):
        if sep in text.rstrip(sep):
            text = text.rstrip(sep).rsplit(sep, 1)[-1]
    return text
