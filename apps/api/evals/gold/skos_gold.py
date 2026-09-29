"""A SKOS taxonomy (an RDF graph of `skos:Concept`s) as a gold tree.

- `skos:broader` and `skos:narrower` give the tree; a concept with several broader concepts
  keeps them all. A top concept of a scheme (`skos:hasTopConcept`, `skos:topConceptOf`) and a
  concept with no broader one hang off the company root; a concept whose label is the company's
  name is the root itself. The default action is "has": the broader concept has the narrower one.
- Labels are `skos:prefLabel` (English first, else the first), else `rdfs:label`, else the
  local name humanised; `skos:altLabel`s (English, else all) are aliases.
- A verb annotation (`birthAction`, `acceptedAction` in any namespace) on a concept gives its
  actions, birth action first.
- A triple between two concepts through any other property is a relation; the verb is the
  property's birth action, else its `rdfs:label`, else its local name, with its accepted and
  inverse actions. `skos:related` gives "is related to" for pairs no such triple links.
- Every other triple is reported under its predicate.
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from evals.gold.common import Actions, clean, finish, humanise, key, relation, verb_from_name
from evals.gold.gold_tree import GoldTree
from evals.gold.ontology_facts import Label, local_name, pick_label
from evals.gold.rdf_gold import alt_labels, verb_annotations
from evals.teach_case import ExpectedConcept, ExpectedRelation

_READ = frozenset(
    {
        RDF.type,
        SKOS.broader,
        SKOS.narrower,
        SKOS.prefLabel,
        SKOS.altLabel,
        SKOS.related,
        SKOS.hasTopConcept,
        SKOS.topConceptOf,
        SKOS.inScheme,
        RDFS.label,
    }
)


def is_skos(graph: Graph) -> bool:
    """True when SKOS concepts outnumber OWL/RDFS classes."""
    concepts = set(graph.subjects(RDF.type, SKOS.Concept))
    concepts.update(graph.subjects(SKOS.broader, None))
    concepts.update(graph.objects(None, SKOS.narrower))
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    return len(concepts) > len(classes)


def import_skos(graph: Graph, company: str, fmt: str = "skos") -> GoldTree:
    concepts = {c for c in graph.subjects(RDF.type, SKOS.Concept) if isinstance(c, URIRef)}
    broader: dict[URIRef, set[URIRef]] = {}
    for child, parent in graph.subject_objects(SKOS.broader):
        broader.setdefault(child, set()).add(parent)
    for parent, child in graph.subject_objects(SKOS.narrower):
        broader.setdefault(child, set()).add(parent)
    for pair in broader.items():
        concepts.update(n for n in (pair[0], *pair[1]) if isinstance(n, URIRef))
    top = set(graph.objects(None, SKOS.hasTopConcept)) | set(
        graph.subjects(SKOS.topConceptOf, None)
    )

    def label_of(node: URIRef) -> str:
        chosen = pick_label(_labels(graph, node, SKOS.prefLabel)) or pick_label(
            _labels(graph, node, RDFS.label)
        )
        return clean(chosen) if chosen else humanise(local_name(str(node)))

    roots = {c for c in concepts if key(label_of(c)) == key(company)}
    annotations, annotation_predicates = verb_annotations(graph)

    def node_label(node: URIRef) -> str:
        return company if node in roots else label_of(node)

    expected: list[ExpectedConcept] = []
    for c in sorted(concepts - roots, key=str):
        parents = sorted(node_label(p) for p in broader.get(c, set()) if p in concepts)
        if c in top or not parents:
            parents.append(company)
        expected.append(
            ExpectedConcept(
                label=label_of(c),
                parent=parents,
                action=annotations.get(str(c), Actions()).listed("has"),
                aliases=alt_labels(graph, c),
            )
        )

    # A triple between two concepts through any other property is a relation.
    relations: list[ExpectedRelation] = []
    linked: set[frozenset[URIRef]] = set()
    properties: set[URIRef] = set()
    for s, pred, o in sorted(graph, key=str):
        if pred in _READ or pred in annotation_predicates:
            continue
        if s in concepts and o in concepts and isinstance(pred, URIRef):
            found = annotations.get(str(pred), Actions())
            verb = _property_verb(graph, pred)
            relations.append(
                relation(node_label(s), node_label(o), found.listed(verb), found.inverse)
            )
            linked.add(frozenset((s, o)))
            properties.add(pred)
    # skos:related is a relation of its own unless a property already links the pair.
    for s, o in graph.subject_objects(SKOS.related):
        if s in concepts and o in concepts and frozenset((s, o)) not in linked:
            relations.append(relation(node_label(s), node_label(o), ["is related to"]))

    ignored: dict[str, int] = {}
    for _, pred, _ in graph:
        if pred not in _READ and pred not in annotation_predicates and pred not in properties:
            name = graph.namespace_manager.normalizeUri(pred)
            ignored[name] = ignored.get(name, 0) + 1
    report: dict[str, object] = {
        "skosConcepts": len(concepts - roots),
        "conceptSchemes": len(set(graph.subjects(RDF.type, SKOS.ConceptScheme))),
        "topConcepts": len(top),
        "ignoredAxioms": dict(sorted(ignored.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    return finish(expected, relations, [], report, company, fmt)


def _labels(graph: Graph, node: URIRef, predicate: URIRef) -> list[Label]:
    return [
        (str(lit), lit.language)
        for lit in graph.objects(node, predicate)
        if isinstance(lit, Literal)
    ]


def _property_verb(graph: Graph, prop: URIRef) -> str:
    chosen = pick_label(_labels(graph, prop, RDFS.label))
    return clean(chosen).lower() if chosen else verb_from_name(local_name(str(prop)))
