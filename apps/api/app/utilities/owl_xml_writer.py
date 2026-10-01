"""OWL 2 OWL/XML serialisation of an export graph.

rdflib writes no OWL/XML, so the export's triples are written here, axiom by axiom, in the
shapes the export mapping produces: declarations, `SubClassOf` a class or an
`ObjectSomeValuesFrom`, `EquivalentClasses`, object property domains and ranges (a class or an
`ObjectUnionOf`), data property domains and ranges, class assertions of named individuals, and
annotation assertions (ontology annotations first). Every IRI is written in full and every text
through the XML serialiser, so no label can become markup. Declarations are sorted and axioms
follow the graph's order, so the same graph gives the same file.
"""

from __future__ import annotations

from collections.abc import Iterator

from rdflib import BNode, Literal, URIRef

from app.utilities import rdf_terms as T
from app.utilities.rdf_writers import xml_attr, xml_text
from app.utilities.triple_index import Node, Triple, TripleIndex

DECLARED_TYPES = {
    T.OWL_CLASS: "Class",
    T.OWL_OBJECT_PROPERTY: "ObjectProperty",
    T.OWL_DATATYPE_PROPERTY: "DataProperty",
    T.OWL_ANNOTATION_PROPERTY: "AnnotationProperty",
    T.OWL_NAMED_INDIVIDUAL: "NamedIndividual",
}


def owl_xml(triples: list[Triple], prefixes: dict[str, str]) -> bytes:
    return "".join(_Writer(TripleIndex(triples), prefixes).lines()).encode("utf-8")


class _Writer:
    def __init__(self, index: TripleIndex, prefixes: dict[str, str]) -> None:
        self.index = index
        self.prefixes = prefixes
        self.kinds: dict[URIRef, set[str]] = {}
        for s, p, o in index.triples:
            if p == T.RDF_TYPE and isinstance(s, URIRef) and o in DECLARED_TYPES:
                self.kinds.setdefault(s, set()).add(DECLARED_TYPES[o])
        self.ontology = next(
            (s for s, p, o in index.triples if p == T.RDF_TYPE and o == T.OWL_ONTOLOGY), None
        )

    def lines(self) -> Iterator[str]:
        yield '<?xml version="1.0" encoding="utf-8"?>\n'
        about = f" ontologyIRI={xml_attr(str(self.ontology))}" if self.ontology else ""
        yield f'<Ontology xmlns="{T.OWL_NS}"{about}>\n'
        for prefix, namespace in sorted(self.prefixes.items()):
            yield f"  <Prefix name={xml_attr(prefix)} IRI={xml_attr(namespace)}/>\n"
        if self.ontology is not None:
            for p, o in self.index.pairs(self.ontology):
                if p != T.RDF_TYPE:
                    yield "  <Annotation>" + self._entity("AnnotationProperty", p)
                    yield self._value(o) + "</Annotation>\n"
        for iri in sorted(self.kinds):
            for kind in sorted(self.kinds[iri]):
                yield f"  <Declaration>{self._entity(kind, iri)}</Declaration>\n"
        for subject in self.index.subjects():
            if subject == self.ontology:
                continue
            for p, o in self.index.pairs(subject):
                axiom = self._axiom(subject, p, o)
                if axiom:
                    yield f"  {axiom}\n"
        yield "</Ontology>\n"

    def _axiom(self, s: URIRef, p: Node, o: Node) -> str:
        kinds = self.kinds.get(s, set())
        if p == T.RDF_TYPE:
            if isinstance(o, URIRef) and o not in DECLARED_TYPES and "NamedIndividual" in kinds:
                body = self._entity("Class", o) + self._entity("NamedIndividual", s)
                return f"<ClassAssertion>{body}</ClassAssertion>"
            return ""
        if p == T.RDFS_SUB_CLASS_OF:
            body = self._entity("Class", s) + self._class_expression(o)
            return f"<SubClassOf>{body}</SubClassOf>"
        if p == T.OWL_EQUIVALENT_CLASS:
            body = self._entity("Class", s) + self._class_expression(o)
            return f"<EquivalentClasses>{body}</EquivalentClasses>"
        if p in (T.RDFS_DOMAIN, T.RDFS_RANGE):
            end = "Domain" if p == T.RDFS_DOMAIN else "Range"
            if "ObjectProperty" in kinds:
                body = self._entity("ObjectProperty", s) + self._class_expression(o)
                return f"<ObjectProperty{end}>{body}</ObjectProperty{end}>"
            if "DataProperty" in kinds:
                target = self._entity("Class" if end == "Domain" else "Datatype", o)
                body = self._entity("DataProperty", s) + target
                return f"<DataProperty{end}>{body}</DataProperty{end}>"
            return ""
        body = self._entity("AnnotationProperty", p) + f"<IRI>{xml_text(str(s))}</IRI>"
        return f"<AnnotationAssertion>{body}{self._value(o)}</AnnotationAssertion>"

    def _class_expression(self, node: Node) -> str:
        if isinstance(node, URIRef):
            return self._entity("Class", node)
        if not isinstance(node, BNode):
            raise ValueError("a class expression is a class or a blank node")
        prop = self.index.value(node, T.OWL_ON_PROPERTY)
        filler = self.index.value(node, T.OWL_SOME_VALUES_FROM)
        if prop is not None and filler is not None:
            body = self._entity("ObjectProperty", prop) + self._class_expression(filler)
            return f"<ObjectSomeValuesFrom>{body}</ObjectSomeValuesFrom>"
        members = self.index.value(node, T.OWL_UNION_OF)
        if members is not None:
            body = "".join(self._class_expression(m) for m in self.index.items(members))
            return f"<ObjectUnionOf>{body}</ObjectUnionOf>"
        raise ValueError("unsupported class expression")

    @staticmethod
    def _entity(kind: str, iri: Node) -> str:
        return f"<{kind} IRI={xml_attr(str(iri))}/>"

    @staticmethod
    def _value(value: Node) -> str:
        if isinstance(value, Literal):
            if value.language:
                attribute = f"xml:lang={xml_attr(value.language)}"
            else:
                attribute = f"datatypeIRI={xml_attr(str(value.datatype or T.XSD_STRING))}"
            return f"<Literal {attribute}>{xml_text(str(value))}</Literal>"
        return f"<IRI>{xml_text(str(value))}</IRI>"
