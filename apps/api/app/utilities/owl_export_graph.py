"""The OWL 2 graph of an export snapshot, in the Ontaix mapping, as a list of triples.

One `owl:Ontology`; companies and tenant domains as named individuals of `ox:Company` and
`ox:Domain`; each concept an `owl:Class` with `rdfs:label`, `ox:company` and `ox:domain`, the
company root a class with the company's name and no domain. A specialisation is
`rdfs:subClassOf` its parent; a birth is `ox:bornFrom` the parent with `ox:birthAction` (and
`ox:birthReverse` when reversed) plus the relation axioms of its action, never a subclass. Every
relation with an action is an `owl:ObjectProperty` per distinct action per company, whose domain
and range are the union of the classes it links, with the assertion
`Subject rdfs:subClassOf [ owl:onProperty P ; owl:someValuesFrom Object ]` for each relation.
Equivalences are `owl:equivalentClass`, conflicts the `ox:conflictsWith` annotation. An attribute
read from a source is an `owl:DatatypeProperty` of its class; a taught attribute an annotation
assertion of an `owl:AnnotationProperty` per name. Only asserted structure is written. Blank
nodes get stable ids and every triple is kept once, in first-written order, so the same snapshot
gives the same graph.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import date

from rdflib import BNode, Literal, URIRef

from app.models.export.export_snapshot import ExportConcept, ExportSnapshot
from app.utilities import ontaix_vocabulary as ox
from app.utilities import rdf_terms as T
from app.utilities.export_iris import (
    company_iri,
    concept_iri,
    domain_iri,
    ontology_iri,
    property_iri,
    slug,
    source_attribute_iri,
    taught_attribute_iri,
)
from app.utilities.triple_index import Triple

SOURCE_RANGES = {
    "id": T.XSD_STRING,
    "text": T.XSD_STRING,
    "number": T.XSD_DECIMAL,
    "date": T.XSD_DATE,
    "ref": T.XSD_ANY_URI,
}
_DECIMAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
PREFIXES: dict[str, str] = {
    "owl": T.OWL_NS,
    "rdf": T.RDF_NS,
    "rdfs": T.RDFS_NS,
    "xsd": T.XSD_NS,
    "skos": T.SKOS_NS,
    "ox": ox.OX_NS,
}


def owl_triples(snapshot: ExportSnapshot) -> list[Triple]:
    return _Builder(snapshot).build()


class TripleList(list[Triple]):
    """Triples in the order they are written."""

    def add(self, triple: Triple) -> None:
        self.append(triple)


def taught_literal(attribute_type: str, value: str) -> Literal:
    """The value typed by its attribute type: `xsd:decimal` and `xsd:date` when the value has
    that form, `xsd:string` otherwise."""
    if attribute_type == "number" and _DECIMAL.match(value):
        return Literal(value, datatype=T.XSD_DECIMAL, normalize=False)
    if attribute_type == "date" and _is_date(value):
        return Literal(value, datatype=T.XSD_DATE, normalize=False)
    return Literal(value, datatype=T.XSD_STRING)


class _Builder:
    def __init__(self, snapshot: ExportSnapshot) -> None:
        self.s = snapshot
        self.g = TripleList()
        self.declared: set[URIRef] = set()
        self.base = snapshot.base_iri
        self.company_keys = {
            c.id: c.key for c in [*snapshot.outside_companies, *snapshot.companies]
        }
        self.concepts: dict[uuid.UUID, ExportConcept] = {
            c.id: c for c in [*snapshot.outside, *snapshot.concepts]
        }
        self.slugs: dict[tuple[uuid.UUID, str], dict[str, str]] = defaultdict(dict)
        self.taken: dict[tuple[uuid.UUID, str], set[str]] = defaultdict(set)
        self.blank = 0
        self.iris: dict[uuid.UUID, URIRef] = {}

    def build(self) -> list[Triple]:
        self._ontology()
        self._vocabulary()
        self._companies_and_domains()
        links: list[tuple[uuid.UUID, str, uuid.UUID]] = []
        for concept in self.s.concepts:
            self._concept(concept, links)
        for relation in self.s.relations:
            a, b = self._iri(relation.a_id), self._iri(relation.b_id)
            if relation.kind == "rel":
                links.append((relation.a_id, relation.action, relation.b_id))
            elif relation.kind == "isa":
                self.g.add((a, T.RDFS_SUB_CLASS_OF, b))
            elif relation.kind == "same":
                self.g.add((a, T.OWL_EQUIVALENT_CLASS, b))
            else:
                self.g.add((a, ox.CONFLICTS_WITH, b))
        self._object_properties(links)
        return list(dict.fromkeys(self.g))

    def _ontology(self) -> None:
        g, s = self.g, self.s
        ontology = ontology_iri(self.base, s.scope, s.exported_at)
        g.add((ontology, T.RDF_TYPE, T.OWL_ONTOLOGY))
        g.add(
            (
                ontology,
                T.RDFS_LABEL,
                Literal(f"Ontology Builder export · {s.scope_name}", lang=s.language),
            )
        )
        g.add((ontology, T.OWL_VERSION_INFO, Literal(s.exported_at.isoformat())))
        g.add(
            (
                ontology,
                T.RDFS_COMMENT,
                Literal(
                    f"The approved model of {s.scope_name}, exported from Ontology Builder.",
                    lang=s.language,
                ),
            )
        )

    def _vocabulary(self) -> None:
        for prop in ox.ANNOTATION_PROPERTIES:
            self.g.add((prop, T.RDF_TYPE, T.OWL_ANNOTATION_PROPERTY))
        for cls in ox.CLASSES:
            self.g.add((cls, T.RDF_TYPE, T.OWL_CLASS))

    def _companies_and_domains(self) -> None:
        g, s = self.g, self.s
        for company in s.companies:
            iri = company_iri(self.base, company.key)
            g.add((iri, T.RDF_TYPE, T.OWL_NAMED_INDIVIDUAL))
            g.add((iri, T.RDF_TYPE, ox.COMPANY_CLASS))
            g.add((iri, T.RDFS_LABEL, Literal(company.name, lang=s.language)))
        for domain in s.domains:
            iri = domain_iri(self.base, domain.key)
            g.add((iri, T.RDF_TYPE, T.OWL_NAMED_INDIVIDUAL))
            g.add((iri, T.RDF_TYPE, ox.DOMAIN_CLASS))
            g.add((iri, T.RDFS_LABEL, Literal(domain.name, lang=s.language)))
            g.add((iri, ox.KEY, Literal(domain.key)))
            g.add((iri, ox.COLOR, Literal(domain.color)))
            g.add((iri, ox.OWNER, Literal(domain.owner)))

    def _concept(
        self, concept: ExportConcept, links: list[tuple[uuid.UUID, str, uuid.UUID]]
    ) -> None:
        g, s = self.g, self.s
        iri = self._iri(concept.id)
        key = self.company_keys[concept.company_id]
        g.add((iri, T.RDF_TYPE, T.OWL_CLASS))
        g.add((iri, T.RDFS_LABEL, Literal(concept.label, lang=s.language)))
        g.add((iri, ox.COMPANY, company_iri(self.base, key)))
        if concept.domain_key is not None:
            g.add((iri, ox.DOMAIN, Literal(concept.domain_key)))
        if concept.parent_id is not None and concept.birth != "root":
            parent = self._iri(concept.parent_id)
            g.add((iri, ox.BORN_FROM, parent))
            if concept.birth == "spec":
                g.add((iri, T.RDFS_SUB_CLASS_OF, parent))
                if concept.rule:
                    g.add((iri, ox.RULE, Literal(concept.rule)))
            else:
                action = concept.birth_action or ""
                g.add((iri, ox.BIRTH_ACTION, Literal(action)))
                if concept.birth_reverse:
                    g.add((iri, ox.BIRTH_REVERSE, Literal(True)))
                    links.append((concept.id, action, concept.parent_id))
                else:
                    links.append((concept.parent_id, action, concept.id))
        for attribute in concept.attributes:
            if attribute.taught:
                self._taught_attribute(
                    iri, concept.company_id, attribute.name, attribute.type, attribute.value or ""
                )
            else:
                self._source_attribute(
                    iri, concept, attribute.name, attribute.type, attribute.col, attribute.fill
                )

    def _taught_attribute(
        self, cls: URIRef, company_id: uuid.UUID, name: str, attribute_type: str, value: str
    ) -> None:
        g = self.g
        key = self.company_keys[company_id]
        prop = taught_attribute_iri(self.base, key, self._slug(company_id, "a", name))
        if prop not in self.declared:
            self.declared.add(prop)
            g.add((prop, T.RDF_TYPE, T.OWL_ANNOTATION_PROPERTY))
            g.add((prop, T.RDFS_LABEL, Literal(name, lang=self.s.language)))
            g.add((prop, ox.ATTRIBUTE_TYPE, Literal(attribute_type)))
            g.add((prop, ox.COMPANY, company_iri(self.base, key)))
        g.add((cls, prop, taught_literal(attribute_type, value)))

    def _source_attribute(
        self,
        cls: URIRef,
        concept: ExportConcept,
        name: str,
        attribute_type: str,
        col: str | None,
        fill: int | None,
    ) -> None:
        g = self.g
        key = self.company_keys[concept.company_id]
        prop = source_attribute_iri(self.base, key, concept.id, slug(name))
        g.add((prop, T.RDF_TYPE, T.OWL_DATATYPE_PROPERTY))
        g.add((prop, T.RDFS_LABEL, Literal(name, lang=self.s.language)))
        g.add((prop, T.RDFS_DOMAIN, cls))
        g.add((prop, T.RDFS_RANGE, SOURCE_RANGES.get(attribute_type, T.XSD_STRING)))
        g.add((prop, ox.COMPANY, company_iri(self.base, key)))
        if col is not None:
            g.add((prop, ox.COLUMN, Literal(col)))
        if fill is not None:
            g.add((prop, ox.FILL, Literal(fill)))

    def _object_properties(self, links: list[tuple[uuid.UUID, str, uuid.UUID]]) -> None:
        """One property per distinct action per company of the subject, with its domain, range
        and one existential restriction per relation."""
        g = self.g
        grouped: dict[tuple[uuid.UUID, str], list[tuple[uuid.UUID, uuid.UUID]]] = defaultdict(list)
        for a_id, action, b_id in links:
            grouped[(self.concepts[a_id].company_id, action)].append((a_id, b_id))
        for (company_id, action), pairs in grouped.items():
            key = self.company_keys[company_id]
            prop = property_iri(self.base, key, self._slug(company_id, "p", action))
            g.add((prop, T.RDF_TYPE, T.OWL_OBJECT_PROPERTY))
            g.add((prop, T.RDFS_LABEL, Literal(action, lang=self.s.language)))
            g.add((prop, ox.COMPANY, company_iri(self.base, key)))
            g.add((prop, T.RDFS_DOMAIN, self._union([a for a, _ in pairs])))
            g.add((prop, T.RDFS_RANGE, self._union([b for _, b in pairs])))
            for a_id, b_id in pairs:
                restriction = self._bnode()
                g.add((restriction, T.RDF_TYPE, T.OWL_RESTRICTION))
                g.add((restriction, T.OWL_ON_PROPERTY, prop))
                g.add((restriction, T.OWL_SOME_VALUES_FROM, self._iri(b_id)))
                g.add((self._iri(a_id), T.RDFS_SUB_CLASS_OF, restriction))

    def _union(self, ids: list[uuid.UUID]) -> URIRef | BNode:
        """One class, or the `owl:unionOf` of several, in first-seen order."""
        classes = [self._iri(i) for i in dict.fromkeys(ids)]
        if len(classes) == 1:
            return classes[0]
        union = self._bnode()
        self.g.add((union, T.RDF_TYPE, T.OWL_CLASS))
        cells = [self._bnode() for _ in classes]
        for n, (cell, cls) in enumerate(zip(cells, classes, strict=True)):
            self.g.add((cell, T.RDF_FIRST, cls))
            self.g.add((cell, T.RDF_REST, cells[n + 1] if n + 1 < len(cells) else T.RDF_NIL))
        self.g.add((union, T.OWL_UNION_OF, cells[0]))
        return union

    def _iri(self, concept_id: uuid.UUID) -> URIRef:
        found = self.iris.get(concept_id)
        if found is None:
            concept = self.concepts[concept_id]
            found = concept_iri(self.base, self.company_keys[concept.company_id], concept.id)
            self.iris[concept_id] = found
        return found

    def _slug(self, company_id: uuid.UUID, kind: str, text: str) -> str:
        """The slug of an action or attribute name, made unique within its company."""
        known, taken = self.slugs[(company_id, kind)], self.taken[(company_id, kind)]
        if text in known:
            return known[text]
        base = slug(text)
        candidate, n = base, 1
        while candidate in taken:
            n += 1
            candidate = f"{base}-{n}"
        known[text] = candidate
        taken.add(candidate)
        return candidate

    def _bnode(self) -> BNode:
        self.blank += 1
        return BNode(f"b{self.blank}")


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10
