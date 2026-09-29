"""An OWL ontology serialised as RDF (Turtle, RDF/XML, JSON-LD, N-Triples, N3) as a gold tree.

The graph is read into `OntologyFacts`, which builds the tree:

- Classes are subjects typed `owl:Class` or `rdfs:Class` and both ends of `rdfs:subClassOf`.
- Object properties are typed `owl:ObjectProperty` (or `rdf:Property` with a class range).
  `rdfs:domain`/`rdfs:range` name a class or an `owl:unionOf` of classes.
- Restrictions under `rdfs:subClassOf` give relations: `owl:someValuesFrom`,
  `owl:allValuesFrom`, `owl:onClass` with a cardinality, `owl:hasValue` naming an individual.
  A restriction on a datatype property or with a datatype filler is reported, not read.
- Verb annotations (`birthAction`, `acceptedAction`, `inverseAction` in any namespace) and
  `skos:altLabel` aliases are read on classes and properties.
- Every triple the import does not read is reported under its predicate: axioms such as
  `owl:disjointWith` or `owl:equivalentClass`, annotations, data assertions.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from evals.gold.common import Actions, action_annotation, clean
from evals.gold.gold_tree import GoldTree
from evals.gold.ontology_facts import OntologyFacts, build_tree, local_name

# rdflib parser names by file suffix; RDF/XML is "xml".
RDF_FORMATS = {
    ".ttl": "turtle",
    ".nt": "nt",
    ".n3": "n3",
    ".jsonld": "json-ld",
    ".json": "json-ld",
    ".rdf": "xml",
    ".owl": "xml",
    ".xml": "xml",
}

_CLASS_TYPES = (OWL.Class, RDFS.Class)
_OBJECT_PROPERTY_TYPES = (
    OWL.ObjectProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    OWL.InverseFunctionalProperty,
)
_FILLERS = (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass)
_DATA_FILLERS = (OWL.onDataRange,)
_CARDINALITIES = (
    OWL.cardinality,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.qualifiedCardinality,
    OWL.minQualifiedCardinality,
    OWL.maxQualifiedCardinality,
)
# Predicates always read (their triples are never reported as ignored).
_READ = frozenset({RDF.type, RDFS.subClassOf, RDFS.label, RDFS.domain, RDFS.range})


def parse_graph(path: Path, rdf_format: str | None = None) -> Graph:
    graph = Graph()
    graph.parse(path, format=rdf_format or RDF_FORMATS.get(path.suffix.lower()))
    return graph


def load_rdf(path: Path, company: str, rdf_format: str | None = None) -> GoldTree:
    fmt = rdf_format or RDF_FORMATS.get(path.suffix.lower(), "turtle")
    return import_graph(parse_graph(path, fmt), company, fmt)


def import_graph(graph: Graph, company: str, fmt: str = "rdf") -> GoldTree:
    """The expected tree, relations and optional leaves of an OWL ontology graph."""
    return build_tree(graph_facts(graph), company, fmt)


def graph_facts(graph: Graph) -> OntologyFacts:
    facts = OntologyFacts()
    nm = graph.namespace_manager
    facts.classes = {str(c) for c in _classes(graph)}
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    object_properties = {
        p for kind in _OBJECT_PROPERTY_TYPES for p in graph.subjects(RDF.type, kind)
    }
    for p in graph.subjects(RDF.type, RDF.Property):
        ranges = {str(r) for r in graph.objects(p, RDFS.range)}
        if ranges & facts.classes:
            object_properties.add(p)
        elif ranges and all(_is_datatype(URIRef(r)) for r in ranges):
            datatype_properties.add(p)
    object_properties = {p for p in object_properties if isinstance(p, URIRef)}
    datatype_properties = {p for p in datatype_properties if isinstance(p, URIRef)}
    datatype_properties -= object_properties
    facts.object_properties = {str(p) for p in object_properties}
    facts.datatype_properties = {str(p) for p in datatype_properties}

    individuals = {str(s) for s in graph.subjects(RDF.type, OWL.NamedIndividual)}
    for s, o in graph.subject_objects(RDF.type):
        if isinstance(s, URIRef) and str(o) in facts.classes:
            individuals.add(str(s))
    facts.individuals = individuals

    for s, lit in graph.subject_objects(RDFS.label):
        if isinstance(s, URIRef) and isinstance(lit, Literal):
            facts.labels.setdefault(str(s), []).append((str(lit), lit.language))
    facts.actions, annotation_predicates = verb_annotations(graph)
    for c in facts.classes:
        aliases = alt_labels(graph, URIRef(c))
        if aliases:
            facts.aliases[c] = aliases

    consumed: set[BNode] = set()
    for c in sorted(_classes(graph), key=str):
        for sup in graph.objects(c, RDFS.subClassOf):
            if isinstance(sup, URIRef):
                if sup != OWL.Thing:
                    facts.superclasses.setdefault(str(c), set()).add(str(sup))
            elif (sup, RDF.type, OWL.Restriction) in graph:
                _read_restriction(graph, str(c), sup, datatype_properties, facts, consumed)
            else:
                facts.ignored["rdfs:subClassOf (complex class expression)"] += 1

    for p in object_properties:
        for predicate, target in ((RDFS.domain, facts.domains), (RDFS.range, facts.ranges)):
            for node in graph.objects(p, predicate):
                members = _class_members(graph, node, consumed)
                if members is None:
                    facts.ignored[f"{nm.normalizeUri(predicate)} (complex class expression)"] += 1
                    continue
                target.setdefault(str(p), set()).update(members)
        for s, o in graph.subject_objects(p):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                facts.assertions.append((str(s), str(p), str(o)))

    # Union domains of datatype properties are read along with the property, which is reported.
    for p in datatype_properties:
        for node in graph.objects(p, RDFS.domain):
            _class_members(graph, node, consumed)

    read = _READ | annotation_predicates | {SKOS.altLabel}
    for s, pred, _ in graph:
        if pred in read or s in consumed or pred in object_properties:
            continue
        name = nm.normalizeUri(pred)
        if pred in datatype_properties:
            facts.ignored[f"data assertion {name}"] += 1
        elif str(s) in individuals:
            facts.ignored[f"individual assertion {name}"] += 1
        else:
            facts.ignored[name] += 1
    return facts


def verb_annotations(graph: Graph) -> tuple[dict[str, Actions], set[URIRef]]:
    """The verb annotations (`birthAction`, `acceptedAction`, `inverseAction`, in any
    namespace) of every subject, and the predicates that carry them."""
    predicates = {
        p for p in set(graph.predicates()) if action_annotation(local_name(str(p))) is not None
    }
    found: dict[str, Actions] = {}
    for p in predicates:
        kind = action_annotation(local_name(str(p))) or ""
        for s, value in sorted(graph.subject_objects(p), key=str):
            if isinstance(s, URIRef) and isinstance(value, Literal):
                found.setdefault(str(s), Actions()).add(kind, str(value))
    return found, predicates


def alt_labels(graph: Graph, node: URIRef) -> list[str]:
    """`skos:altLabel`s, English (or untagged) first; all of them when none is English."""
    labels = [lit for lit in graph.objects(node, SKOS.altLabel) if isinstance(lit, Literal)]
    english = [x for x in labels if (x.language or "en").lower().startswith("en")]
    return sorted(clean(str(x)) for x in (english or labels))


def _classes(graph: Graph) -> set[URIRef]:
    found: set[URIRef] = set()
    for kind in _CLASS_TYPES:
        found.update(s for s in graph.subjects(RDF.type, kind) if isinstance(s, URIRef))
    for s, o in graph.subject_objects(RDFS.subClassOf):
        found.update(n for n in (s, o) if isinstance(n, URIRef))
    return {c for c in found if c != OWL.Thing and not _is_datatype(c)}


def _is_datatype(node: URIRef) -> bool:
    return str(node).startswith(str(XSD)) or node in (RDFS.Literal, RDFS.Datatype, RDF.langString)


def _class_members(graph: Graph, node: object, consumed: set[BNode]) -> list[str] | None:
    """A named class, or the members of an `owl:unionOf` of named classes; None otherwise."""
    if isinstance(node, URIRef):
        return [str(node)]
    union = graph.value(node, OWL.unionOf) if isinstance(node, BNode) else None
    if union is None:
        return None
    members = list(Collection(graph, union))
    if not all(isinstance(m, URIRef) for m in members):
        return None
    consumed.add(node)
    consumed.update(_list_nodes(graph, union))
    return [str(m) for m in members]


def _list_nodes(graph: Graph, head: object) -> list[BNode]:
    nodes: list[BNode] = []
    while isinstance(head, BNode) and head not in nodes:
        nodes.append(head)
        head = graph.value(head, RDF.rest)
    return nodes


def _read_restriction(
    graph: Graph,
    owner: str,
    node: BNode,
    datatype_properties: set[URIRef],
    facts: OntologyFacts,
    consumed: set[BNode],
) -> None:
    prop = graph.value(node, OWL.onProperty)
    if not isinstance(prop, URIRef):
        facts.ignored["owl:Restriction (complex property)"] += 1
        return
    fillers = [graph.value(node, p) for p in (*_FILLERS, OWL.hasValue, *_DATA_FILLERS)]
    fillers = [f for f in fillers if f is not None]
    is_data = (
        prop in datatype_properties
        or any(graph.value(node, p) is not None for p in _DATA_FILLERS)
        or any(
            isinstance(f, Literal) or (isinstance(f, URIRef) and _is_datatype(f)) for f in fillers
        )
    )
    if is_data:
        facts.datatype_restrictions.append((owner, str(prop)))
        consumed.add(node)
        return
    named = [f for f in fillers if isinstance(f, URIRef)]
    if named:
        facts.restrictions.append((owner, str(prop), str(named[0])))
        consumed.add(node)
    elif not fillers and any(graph.value(node, c) is not None for c in _CARDINALITIES):
        facts.ignored["owl:Restriction (unqualified cardinality)"] += 1
        consumed.add(node)
    else:
        facts.ignored["owl:Restriction (complex filler)"] += 1
