"""RDF graphs (RDF/XML, Turtle, JSON-LD, N-Triples) read as classes, properties and statements.

The graph is parsed by rdflib from the uploaded text alone. XML is first checked with no DTD
and no entities, so the RDF/XML parser never meets one; a JSON-LD `@context` given by URL or
through `@import` is refused before parsing, so no context is ever fetched; `owl:imports` is
only reported. Nothing is inferred: named classes are those typed `owl:Class`, `rdfs:Class` or
`skos:Concept`, those with an asserted `rdfs:subClassOf` or `skos:broader`, and parents that
are described in the file. At most 1,000,000 triples.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterable
from typing import Any

import defusedxml.ElementTree as DefusedET
from defusedxml import DefusedXmlException
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from app.models.ontology_import.parsed_ontology import (
    ALT_LABEL,
    PREF_LABEL,
    RDFS_LABEL,
    LabelLiteral,
    OntologyFormat,
    OntologyItem,
    OntologyProperty,
    OntologyStatement,
    ParsedOntology,
    SkippedSource,
)
from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.document_text import decode_text

MAX_TRIPLES = 1_000_000

RDFLIB_FORMATS: dict[str, str] = {
    "rdf_xml": "xml",
    "turtle": "turtle",
    "json_ld": "json-ld",
    "n_triples": "nt",
}
LABEL_PREDICATES = (
    (SKOS.prefLabel, PREF_LABEL),
    (RDFS.label, RDFS_LABEL),
    (SKOS.altLabel, ALT_LABEL),
)
CLASS_TYPES = (OWL.Class, RDFS.Class, SKOS.Concept)
TOP_CLASSES = (OWL.Thing, RDFS.Resource, OWL.Nothing)
EQUIVALENCES = (OWL.equivalentClass, OWL.sameAs, SKOS.exactMatch)
UNSUPPORTED_ON_CLASS = (
    OWL.unionOf,
    OWL.intersectionOf,
    OWL.complementOf,
    OWL.oneOf,
    OWL.disjointWith,
    OWL.disjointUnionOf,
    OWL.hasKey,
)
RESTRICTION_FILLERS = (OWL.someValuesFrom, OWL.allValuesFrom)


def read_rdf(data: bytes, fmt: OntologyFormat) -> ParsedOntology:
    """The classes, properties and statements of an RDF file."""
    text = decode_text(data)
    if fmt == "rdf_xml":
        _check_xml(data)
    if fmt == "json_ld":
        _check_json_ld(text)
    graph = Graph()
    try:
        graph.parse(data=text, format=RDFLIB_FORMATS[fmt])
    except (DocumentTooLargeError, DocumentUnreadableError):
        raise
    except Exception as exc:
        raise DocumentUnreadableError(
            f"the {fmt.replace('_', ' ')} file could not be read"
        ) from exc
    if len(graph) > MAX_TRIPLES:
        raise DocumentTooLargeError(f"more than {MAX_TRIPLES} triples")
    return _Reader(graph, fmt).read()


def local_name(iri: str) -> str:
    """The last segment of an IRI, after its last `#`, `/` or `:`."""
    for separator in ("#", "/", ":"):
        if separator in iri:
            tail = iri.rsplit(separator, 1)[1]
            if tail:
                return tail
    return iri


class _Reader:
    def __init__(self, graph: Graph, fmt: OntologyFormat) -> None:
        self.graph = graph
        self.parsed = ParsedOntology(format=fmt)

    def read(self) -> ParsedOntology:
        g = self.graph
        for imported in sorted(str(o) for o in g.objects(None, OWL.imports)):
            self._skip(imported, "remote_import_not_fetched")
        classes = self._classes()
        items: dict[URIRef, OntologyItem] = {}
        for cls in sorted(classes, key=str):
            items[cls] = self._item(cls, individual=False)
        for cls in sorted(classes, key=str):
            self._class_axioms(cls, items[cls], classes)
        for broader in sorted(
            (s for s in g.subjects(SKOS.narrower, None) if isinstance(s, URIRef)), key=str
        ):
            for narrower in g.objects(broader, SKOS.narrower):
                if narrower in items and broader in classes and narrower != broader:
                    parent = (str(broader), "includes")
                    if parent not in items[narrower].parents:
                        items[narrower].parents.append(parent)
        self._properties(classes)
        self._individuals(classes, items)
        self.parsed.items.extend(items.values())
        self.parsed.items.sort(key=lambda i: i.source)
        return self.parsed

    def _classes(self) -> set[URIRef]:
        g = self.graph
        found: set[URIRef] = set()
        for kind in CLASS_TYPES:
            found.update(s for s in g.subjects(RDF.type, kind) if isinstance(s, URIRef))
        described = {s for s in g.subjects() if isinstance(s, URIRef)}
        for predicate in (RDFS.subClassOf, SKOS.broader, SKOS.narrower):
            found.update(s for s in g.subjects(predicate, None) if isinstance(s, URIRef))
            found.update(
                o for o in g.objects(None, predicate) if isinstance(o, URIRef) and o in described
            )
        return {c for c in found if c not in TOP_CLASSES and not self._is_property(c)}

    def _is_property(self, node: URIRef) -> bool:
        types = set(self.graph.objects(node, RDF.type))
        return bool(
            types & {OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property}
        )

    def _item(self, node: URIRef, individual: bool) -> OntologyItem:
        item = OntologyItem(
            source=str(node), individual=individual, local_name=local_name(str(node))
        )
        for predicate, prop in LABEL_PREDICATES:
            for literal in _literals(self.graph.objects(node, predicate)):
                item.add_label(prop, literal)
        return item

    def _class_axioms(
        self,
        cls: URIRef,
        item: OntologyItem,
        classes: set[URIRef],
    ) -> None:
        g = self.graph
        for predicate in EQUIVALENCES:
            if any(True for _ in g.objects(cls, predicate)):
                self._skip(str(cls), "equivalence_not_imported")
                break
        if any(True for p in UNSUPPORTED_ON_CLASS for _ in g.objects(cls, p)):
            self._skip(str(cls), "unsupported_axiom")
        for parent in sorted(g.objects(cls, RDFS.subClassOf), key=str):
            if isinstance(parent, URIRef):
                if parent in classes and parent != cls:
                    item.parents.append((str(parent), "spec"))
            elif isinstance(parent, BNode):
                self._restriction(cls, parent)
        for parent in sorted(g.objects(cls, SKOS.broader), key=str):
            if isinstance(parent, URIRef) and parent in classes and parent != cls:
                entry = (str(parent), "includes")
                if entry not in item.parents:
                    item.parents.append(entry)

    def _restriction(self, cls: URIRef, node: BNode) -> None:
        g = self.graph
        prop = g.value(node, OWL.onProperty)
        filler = next(
            (g.value(node, p) for p in RESTRICTION_FILLERS if g.value(node, p) is not None), None
        )
        if isinstance(prop, URIRef) and isinstance(filler, URIRef) and filler not in TOP_CLASSES:
            self._property(prop)
            self.parsed.statements.append(OntologyStatement(str(cls), str(prop), str(filler)))
            return
        self._skip(str(cls), "unsupported_axiom")

    def _properties(self, classes: set[URIRef]) -> None:
        g = self.graph
        for prop in sorted(
            (s for s in g.subjects(RDF.type, OWL.DatatypeProperty) if isinstance(s, URIRef)),
            key=str,
        ):
            self._skip(str(prop), "datatype_property")
        for prop in sorted(
            (s for s in g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(s, URIRef)), key=str
        ):
            entry = self._property(prop)
            if any(True for _ in g.objects(prop, OWL.propertyChainAxiom)):
                self._skip(str(prop), "unsupported_axiom")
            for domain in sorted(g.objects(prop, RDFS.domain), key=str):
                if isinstance(domain, URIRef) and domain in classes:
                    entry.domains.append(str(domain))
                elif isinstance(domain, BNode):
                    self._skip(str(prop), "unsupported_axiom")
            for rng in sorted(g.objects(prop, RDFS.range), key=str):
                if isinstance(rng, URIRef) and rng in classes:
                    entry.ranges.append(str(rng))
                elif isinstance(rng, BNode):
                    self._skip(str(prop), "unsupported_axiom")

    def _property(self, prop: URIRef) -> OntologyProperty:
        found = self.parsed.properties.get(str(prop))
        if found is not None:
            return found
        entry = OntologyProperty(source=str(prop), local_name=local_name(str(prop)))
        for predicate, name in LABEL_PREDICATES:
            for literal in _literals(self.graph.objects(prop, predicate)):
                entry.add_label(name, literal)
        self.parsed.properties[str(prop)] = entry
        return entry

    def _individuals(self, classes: set[URIRef], items: dict[URIRef, OntologyItem]) -> None:
        g = self.graph
        candidates: set[URIRef] = {
            s for s in g.subjects(RDF.type, OWL.NamedIndividual) if isinstance(s, URIRef)
        }
        for cls in classes:
            candidates.update(s for s in g.subjects(RDF.type, cls) if isinstance(s, URIRef))
        for node in sorted(candidates - classes, key=str):
            if self._is_property(node) or node in items:
                continue
            item = self._item(node, individual=True)
            for cls in sorted(g.objects(node, RDF.type), key=str):
                if isinstance(cls, URIRef) and cls in classes:
                    item.parents.append((str(cls), "instance"))
            if any(True for _ in g.objects(node, OWL.sameAs)):
                self._skip(str(node), "equivalence_not_imported")
            items[node] = item

    def _skip(self, source: str, reason: Any) -> None:
        entry = SkippedSource(source, reason)
        if entry not in self.parsed.skipped:
            self.parsed.skipped.append(entry)


def _literals(values: Iterable[Any]) -> list[LabelLiteral]:
    """Literal values in a stable order: by language tag, then text."""
    found = [
        LabelLiteral(str(v), v.language.lower() if v.language else None)
        for v in values
        if isinstance(v, Literal)
    ]
    return sorted(found, key=lambda lit: (lit.language or "", lit.text))


def _check_xml(data: bytes) -> None:
    """Refuse XML that declares a DTD or entities before rdflib's parser sees it."""
    try:
        for _ in DefusedET.iterparse(
            io.BytesIO(data),
            events=("start",),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            pass
    except DefusedXmlException as exc:
        raise DocumentUnreadableError("XML with a DTD or entities is not read") from exc
    except DefusedET.ParseError as exc:
        raise DocumentUnreadableError("the XML is not well-formed") from exc


def _check_json_ld(text: str) -> None:
    """Refuse a JSON-LD document whose context would be fetched: a context given by URL, or a
    context holding `@import`."""
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise DocumentUnreadableError("the file is not JSON") from exc
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            for key, child in node.items():
                if key == "@context":
                    _check_context(child)
                stack.append(child)


def _check_context(context: Any) -> None:
    contexts = context if isinstance(context, list) else [context]
    for entry in contexts:
        if isinstance(entry, str):
            raise DocumentUnreadableError("a remote JSON-LD @context is never fetched")
        if isinstance(entry, dict) and "@import" in entry:
            raise DocumentUnreadableError("a remote JSON-LD @context is never fetched")
