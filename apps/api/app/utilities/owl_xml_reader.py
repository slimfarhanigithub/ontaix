"""OWL/XML ontologies read as classes, properties and statements, with no DTD and no entities.

Declarations give the named classes, object properties and individuals; `SubClassOf` between
named classes gives parents, and a `SubClassOf` whose super class is an
`ObjectSomeValuesFrom` or `ObjectAllValuesFrom` of a named property and class gives a
statement; `ObjectPropertyDomain` and `ObjectPropertyRange` give a property's ends;
`ClassAssertion` types an individual; `AnnotationAssertion` of `rdfs:label`, `skos:prefLabel`
or `skos:altLabel` gives labels. Equivalences, imports, data properties and every other axiom
are reported, never reasoned over.
"""

from __future__ import annotations

from typing import Any

import defusedxml.ElementTree as DefusedET
from defusedxml import DefusedXmlException

from app.models.ontology_import.parsed_ontology import (
    ALT_LABEL,
    PREF_LABEL,
    RDFS_LABEL,
    LabelLiteral,
    OntologyItem,
    OntologyProperty,
    OntologyStatement,
    ParsedOntology,
    SkippedSource,
    SkipReason,
)
from app.utilities.document_errors import DocumentUnreadableError
from app.utilities.rdf_ontology_reader import local_name

OWL = "{http://www.w3.org/2002/07/owl#}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
SKOS_NS = "http://www.w3.org/2004/02/skos/core#"
OWL_NS = "http://www.w3.org/2002/07/owl#"
LABEL_ANNOTATIONS = {
    SKOS_NS + "prefLabel": PREF_LABEL,
    RDFS_NS + "label": RDFS_LABEL,
    SKOS_NS + "altLabel": ALT_LABEL,
}
TOP_CLASSES = {OWL_NS + "Thing", OWL_NS + "Nothing"}
IGNORED_AXIOMS = {
    "Prefix",
    "Declaration",
    "AnnotationAssertion",
    "Annotation",
    "SubAnnotationPropertyOf",
    "AnnotationPropertyDomain",
    "AnnotationPropertyRange",
}
DATA_AXIOMS = {
    "DataPropertyDomain",
    "DataPropertyRange",
    "SubDataPropertyOf",
    "FunctionalDataProperty",
    "DataPropertyAssertion",
}


def read_owl_xml(data: bytes) -> ParsedOntology:
    try:
        root = DefusedET.fromstring(
            data, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except DefusedXmlException as exc:
        raise DocumentUnreadableError("XML with a DTD or entities is not read") from exc
    except DefusedET.ParseError as exc:
        raise DocumentUnreadableError("the OWL/XML file is not well-formed") from exc
    return _Reader(root).read()


class _Reader:
    def __init__(self, root: Any) -> None:
        self.root = root
        self.prefixes: dict[str, str] = {
            "owl": OWL_NS,
            "rdfs": RDFS_NS,
            "skos": SKOS_NS,
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        }
        self.parsed = ParsedOntology(format="owl_xml")
        self.items: dict[str, OntologyItem] = {}
        self.classes: set[str] = set()
        self.individuals: set[str] = set()

    def read(self) -> ParsedOntology:
        axioms = list(self.root)
        for element in axioms:
            if _name(element) == "Prefix":
                self.prefixes[element.get("name", "")] = element.get("IRI", "")
        for element in axioms:
            if _name(element) == "Import":
                self._skip((element.text or "").strip(), "remote_import_not_fetched")
            elif _name(element) == "Declaration":
                self._declaration(element)
        for element in axioms:
            if _name(element) == "SubClassOf" and len(element) == 2:
                for child in element:
                    if _name(child) == "Class":
                        self.classes.add(self._iri(child))
        for iri in self.classes:
            self._item(iri, individual=False)
        for iri in self.individuals - self.classes:
            self._item(iri, individual=True)
        for element in axioms:
            self._axiom(element)
        self.parsed.items = sorted(self.items.values(), key=lambda i: i.source)
        return self.parsed

    def _declaration(self, element: Any) -> None:
        for child in element:
            kind, iri = _name(child), self._iri(child)
            if not iri:
                continue
            if kind == "Class" and iri not in TOP_CLASSES:
                self.classes.add(iri)
            elif kind == "ObjectProperty":
                self._property(iri)
            elif kind == "DataProperty":
                self._skip(iri, "datatype_property")
            elif kind == "NamedIndividual":
                self.individuals.add(iri)

    def _axiom(self, element: Any) -> None:
        kind = _name(element)
        children = list(element)
        if kind in IGNORED_AXIOMS or kind in DATA_AXIOMS or kind == "Import":
            if kind == "AnnotationAssertion":
                self._annotation(children)
            return
        if kind == "SubClassOf" and len(children) == 2 and _name(children[0]) == "Class":
            self._sub_class(self._iri(children[0]), children[1])
            return
        if kind in ("EquivalentClasses", "SameIndividual"):
            for child in children:
                if _name(child) in ("Class", "NamedIndividual"):
                    self._skip(self._iri(child), "equivalence_not_imported")
                    return
        if kind in ("ObjectPropertyDomain", "ObjectPropertyRange") and len(children) == 2:
            prop = self._iri(children[0])
            end = self._iri(children[1]) if _name(children[1]) == "Class" else ""
            if _name(children[0]) == "ObjectProperty" and end in self.classes:
                entry = self._property(prop)
                (entry.domains if kind == "ObjectPropertyDomain" else entry.ranges).append(end)
                return
        if kind == "ClassAssertion" and len(children) == 2:
            cls, individual = self._iri(children[0]), self._iri(children[1])
            if _name(children[0]) == "Class" and cls in self.classes and individual:
                item = self._item(individual, individual=True)
                item.parents.append((cls, "instance"))
                return
        self._skip(self._first_iri(element) or kind, "unsupported_axiom")

    def _sub_class(self, cls: str, parent: Any) -> None:
        kind = _name(parent)
        if kind == "Class":
            iri = self._iri(parent)
            if iri in TOP_CLASSES:
                return
            if iri in self.classes and iri != cls:
                self.items[cls].parents.append((iri, "spec"))
            return
        if kind in ("ObjectSomeValuesFrom", "ObjectAllValuesFrom") and len(parent) == 2:
            prop, filler = parent[0], parent[1]
            if _name(prop) == "ObjectProperty" and _name(filler) == "Class":
                self._property(self._iri(prop))
                self.parsed.statements.append(
                    OntologyStatement(cls, self._iri(prop), self._iri(filler))
                )
                return
        self._skip(cls, "unsupported_axiom")

    def _annotation(self, children: list[Any]) -> None:
        if len(children) < 3 or _name(children[0]) != "AnnotationProperty":
            return
        prop = LABEL_ANNOTATIONS.get(self._iri(children[0]))
        subject = self._iri(children[1]) if _name(children[1]) in ("IRI", "AbbreviatedIRI") else ""
        value = children[2]
        if prop is None or not subject or _name(value) != "Literal":
            return
        literal = LabelLiteral(value.text or "", (value.get(XML_LANG) or "").lower() or None)
        if subject in self.items:
            self.items[subject].add_label(prop, literal)
        elif subject in self.parsed.properties:
            self.parsed.properties[subject].add_label(prop, literal)
        elif subject in self.individuals:
            self._item(subject, individual=True).add_label(prop, literal)

    def _item(self, iri: str, individual: bool) -> OntologyItem:
        found = self.items.get(iri)
        if found is None:
            found = OntologyItem(source=iri, individual=individual, local_name=local_name(iri))
            self.items[iri] = found
        return found

    def _property(self, iri: str) -> OntologyProperty:
        found = self.parsed.properties.get(iri)
        if found is None:
            found = OntologyProperty(source=iri, local_name=local_name(iri))
            self.parsed.properties[iri] = found
        return found

    def _iri(self, element: Any) -> str:
        """The full IRI of an entity or IRI element, abbreviated forms expanded."""
        if _name(element) == "IRI":
            return (element.text or "").strip()
        if _name(element) == "AbbreviatedIRI":
            return self._expand((element.text or "").strip())
        if element.get("IRI") is not None:
            return element.get("IRI", "").strip()
        if element.get("abbreviatedIRI") is not None:
            return self._expand(element.get("abbreviatedIRI", "").strip())
        return ""

    def _expand(self, abbreviated: str) -> str:
        prefix, _, rest = abbreviated.partition(":")
        return self.prefixes.get(prefix, prefix + ":") + rest

    def _first_iri(self, element: Any) -> str:
        for node in element.iter():
            iri = self._iri(node) if node is not element else ""
            if iri:
                return iri
        return ""

    def _skip(self, source: str, reason: SkipReason) -> None:
        entry = SkippedSource(source, reason)
        if source and entry not in self.parsed.skipped:
            self.parsed.skipped.append(entry)


def _name(element: Any) -> str:
    """The local name of an element in the OWL namespace; any other element keeps its tag."""
    tag = element.tag if isinstance(element.tag, str) else ""
    return tag[len(OWL) :] if tag.startswith(OWL) else tag
