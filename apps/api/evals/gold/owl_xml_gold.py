"""An OWL ontology in the OWL 2 XML serialisation (root element `Ontology` in the OWL namespace)
as a gold tree.

The axioms are read into `OntologyFacts`, which builds the tree:

- `Declaration` of a `Class`, `ObjectProperty`, `DataProperty` or `NamedIndividual`.
- `SubClassOf` of two named classes gives the tree; with an `ObjectSomeValuesFrom`,
  `ObjectAllValuesFrom`, qualified object cardinality or `ObjectHasValue` superclass it gives a
  relation; a data restriction is reported.
- `ObjectPropertyDomain`/`ObjectPropertyRange` (a class or an `ObjectUnionOf` of classes),
  `ClassAssertion`, `ObjectPropertyAssertion`, and `AnnotationAssertion` of `rdfs:label`,
  `skos:altLabel` (aliases) and verb annotations (`birthAction`, `acceptedAction`,
  `inverseAction` in any namespace).
- Every other axiom is reported under its element name (annotations under their property).

`IRI` attributes resolve against the ontology's `xml:base` (else its IRI) and
`abbreviatedIRI`s against the `Prefix` elements.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from evals.gold.common import action_annotation, clean
from evals.gold.gold_tree import GoldTree
from evals.gold.ontology_facts import OWL_THING, OntologyFacts, build_tree, local_name

OWL_NS = "http://www.w3.org/2002/07/owl#"
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
_SKOS_ALT_LABEL = "http://www.w3.org/2004/02/skos/core#altLabel"
_STANDARD_PREFIXES = {
    "owl": OWL_NS,
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
_OBJECT_FILLERS = frozenset(
    {
        "ObjectSomeValuesFrom",
        "ObjectAllValuesFrom",
        "ObjectMinCardinality",
        "ObjectMaxCardinality",
        "ObjectExactCardinality",
    }
)
_DATA_RESTRICTIONS = frozenset(
    {
        "DataSomeValuesFrom",
        "DataAllValuesFrom",
        "DataHasValue",
        "DataMinCardinality",
        "DataMaxCardinality",
        "DataExactCardinality",
    }
)
_HEADER = frozenset({"Prefix", "Import", "Annotation"})


def load_owl_xml(path: Path, company: str) -> GoldTree:
    root = ElementTree.parse(path).getroot()
    if _local(root.tag) != "Ontology" or not root.tag.startswith(f"{{{OWL_NS}}}"):
        raise ValueError(f"{path.name}: not an OWL/XML ontology (root {root.tag})")
    return build_tree(_Reader(root).facts(), company, "owl-xml")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class _Reader:
    def __init__(self, root: Element) -> None:
        self.root = root
        self.base = root.get(_XML_BASE) or root.get("ontologyIRI") or ""
        self.prefixes = dict(_STANDARD_PREFIXES)
        for el in root:
            if _local(el.tag) == "Prefix":
                self.prefixes[el.get("name", "")] = el.get("IRI", "")
        self.out = OntologyFacts()

    def facts(self) -> OntologyFacts:
        for axiom in self.root:
            name = _local(axiom.tag)
            if name in _HEADER:
                continue
            handler = getattr(self, f"_{name}", None)
            parts = [c for c in axiom if _local(c.tag) != "Annotation"]
            if handler is None:
                self.out.ignored[name] += 1
                continue
            try:
                handler(parts)
            except IndexError:
                self.out.ignored[f"{name} (malformed)"] += 1
        return self.out

    def _iri(self, el: Element) -> str:
        """An entity's `IRI` or `abbreviatedIRI` attribute, or an `IRI`/`AbbreviatedIRI`
        element's text, as a full IRI."""
        if el.get("abbreviatedIRI") is not None:
            return self._expand(el.get("abbreviatedIRI", ""))
        if _local(el.tag) == "AbbreviatedIRI":
            return self._expand((el.text or "").strip())
        text = el.get("IRI")
        return urljoin(self.base, text if text is not None else (el.text or "").strip())

    def _expand(self, abbreviated: str) -> str:
        prefix, _, rest = abbreviated.partition(":")
        return self.prefixes.get(prefix, f"{prefix}:") + rest

    def _qname(self, iri: str) -> str:
        for prefix, ns in sorted(self.prefixes.items(), key=lambda kv: -len(kv[1])):
            if ns and iri.startswith(ns):
                return f"{prefix}:{iri[len(ns) :]}"
        return f"<{iri}>"

    def _Declaration(self, children: list[Element]) -> None:
        for el in children:
            kind = _local(el.tag)
            target = {
                "Class": self.out.classes,
                "ObjectProperty": self.out.object_properties,
                "DataProperty": self.out.datatype_properties,
                "NamedIndividual": self.out.individuals,
            }.get(kind)
            if target is not None:
                target.add(self._iri(el))

    def _SubClassOf(self, children: list[Element]) -> None:
        sub, sup = children[0], children[1]
        if _local(sub.tag) != "Class":
            self.out.ignored["SubClassOf (complex subclass)"] += 1
            return
        owner = self._iri(sub)
        self.out.classes.add(owner)
        kind = _local(sup.tag)
        parts = list(sup)
        if kind == "Class":
            iri = self._iri(sup)
            if iri != OWL_THING:
                self.out.classes.add(iri)
                self.out.superclasses.setdefault(owner, set()).add(iri)
        elif kind in _OBJECT_FILLERS:
            prop = parts[0] if parts else None
            filler = parts[-1] if len(parts) > 1 else None
            if prop is None or _local(prop.tag) != "ObjectProperty":
                self.out.ignored[f"{kind} (complex property)"] += 1
            elif filler is None:
                self.out.ignored[f"{kind} (unqualified)"] += 1
            elif _local(filler.tag) == "Class":
                self.out.restrictions.append((owner, self._iri(prop), self._iri(filler)))
            else:
                self.out.ignored[f"{kind} (complex filler)"] += 1
        elif kind == "ObjectHasValue" and len(parts) == 2:
            self.out.restrictions.append((owner, self._iri(parts[0]), self._iri(parts[1])))
        elif kind in _DATA_RESTRICTIONS and parts:
            self.out.datatype_restrictions.append((owner, self._iri(parts[0])))
        else:
            self.out.ignored["SubClassOf (complex class expression)"] += 1

    def _ObjectPropertyDomain(self, children: list[Element]) -> None:
        self._domain_or_range(children, self.out.domains, "ObjectPropertyDomain")

    def _ObjectPropertyRange(self, children: list[Element]) -> None:
        self._domain_or_range(children, self.out.ranges, "ObjectPropertyRange")

    def _domain_or_range(
        self, children: list[Element], target: dict[str, set[str]], name: str
    ) -> None:
        prop, expr = children[0], children[1]
        if _local(prop.tag) != "ObjectProperty":
            self.out.ignored[f"{name} (complex property)"] += 1
            return
        if _local(expr.tag) == "Class":
            members = [expr]
        elif _local(expr.tag) == "ObjectUnionOf" and all(_local(m.tag) == "Class" for m in expr):
            members = list(expr)
        else:
            self.out.ignored[f"{name} (complex class expression)"] += 1
            return
        prop_iri = self._iri(prop)
        self.out.object_properties.add(prop_iri)
        target.setdefault(prop_iri, set()).update(self._iri(m) for m in members)

    def _ClassAssertion(self, children: list[Element]) -> None:
        cls, ind = children[0], children[-1]
        if _local(ind.tag) == "NamedIndividual":
            self.out.individuals.add(self._iri(ind))
        if _local(cls.tag) != "Class":
            self.out.ignored["ClassAssertion (complex class expression)"] += 1

    def _ObjectPropertyAssertion(self, children: list[Element]) -> None:
        prop, s, o = children[0], children[1], children[2]
        if _local(prop.tag) != "ObjectProperty":
            self.out.ignored["ObjectPropertyAssertion (complex property)"] += 1
            return
        self.out.assertions.append((self._iri(s), self._iri(prop), self._iri(o)))

    def _AnnotationAssertion(self, children: list[Element]) -> None:
        prop, subject, value = children[0], children[1], children[2]
        prop_iri = self._iri(prop)
        literal = _local(value.tag) == "Literal"
        text = (value.text or "").strip()
        kind = action_annotation(local_name(prop_iri))
        if prop_iri == _RDFS_LABEL and literal:
            self.out.labels.setdefault(self._iri(subject), []).append((text, value.get(_XML_LANG)))
        elif kind is not None and literal:
            self.out.annotate(self._iri(subject), kind, text)
        elif prop_iri == _SKOS_ALT_LABEL and literal:
            self.out.aliases.setdefault(self._iri(subject), []).append(clean(text))
        else:
            self.out.ignored[f"AnnotationAssertion {self._qname(prop_iri)}"] += 1
