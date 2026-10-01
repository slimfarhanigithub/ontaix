"""Turtle, RDF/XML and JSON-LD serialisations of an export's triples, in one linear pass.

Each named subject is written once with all its statements; the blank nodes of an export are
referenced once, so a restriction or a union is written inline where it is used and an RDF list
as a collection. Terms are escaped by rdflib (`n3`) for Turtle and by the XML and JSON
serialisers otherwise, so no label or value can break out of its literal. Every file parses back
with rdflib into the same graph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from rdflib import BNode, Literal, URIRef

from app.utilities import rdf_terms as T
from app.utilities.triple_index import Node, Triple, TripleIndex

INDENT = "    "
_TURTLE_LOCAL = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_NC_NAME_TAIL = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*$")
_ATTRIBUTE_SPECIALS = '&<>"\n\r\t'
_ATTRIBUTE_ESCAPES = str.maketrans({'"': "&quot;", "\n": "&#10;", "\r": "&#13;", "\t": "&#9;"})


def xml_text(value: str) -> str:
    """Text escaped for XML character data."""
    if "&" in value or "<" in value or ">" in value:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return value


def xml_attr(value: str) -> str:
    """A double-quoted XML attribute value; line breaks and tabs are kept as references."""
    if any(c in value for c in _ATTRIBUTE_SPECIALS):
        value = xml_text(value).translate(_ATTRIBUTE_ESCAPES)
    return f'"{value}"'


def turtle(triples: list[Triple], prefixes: dict[str, str]) -> bytes:
    return "".join(_TurtleWriter(TripleIndex(triples), prefixes).lines()).encode("utf-8")


def rdf_xml(triples: list[Triple], prefixes: dict[str, str]) -> bytes:
    return "".join(_XmlWriter(TripleIndex(triples), prefixes).lines()).encode("utf-8")


def json_ld(triples: list[Triple], context: dict[str, str]) -> bytes:
    index = TripleIndex(triples)
    writer = _JsonLdWriter(index, context)
    document = {"@context": context, "@graph": [writer.node(s) for s in index.subjects()]}
    return json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8")


class _TurtleWriter:
    def __init__(self, index: TripleIndex, prefixes: dict[str, str]) -> None:
        self.index = index
        self.prefixes = sorted(prefixes.items(), key=lambda p: -len(p[1]))
        self.declared = prefixes

    def lines(self) -> Iterator[str]:
        for prefix, namespace in sorted(self.declared.items()):
            yield f"@prefix {prefix}: <{namespace}> .\n"
        for subject in self.index.subjects():
            yield "\n"
            yield self.term(subject)
            yield self.predicates(subject, 1)
            yield " .\n"

    def predicates(self, subject: Node, depth: int) -> str:
        groups: dict[Node, list[Node]] = {}
        for p, o in self.index.pairs(subject):
            groups.setdefault(p, []).append(o)
        pad = "\n" + INDENT * depth
        parts = []
        for predicate, objects in groups.items():
            name = "a" if predicate == T.RDF_TYPE else self.term(predicate)
            values = ", ".join(self.value(o, depth + 1) for o in objects)
            parts.append(f"{name} {values}")
        return " " + (" ;" + pad).join(parts) if parts else ""

    def value(self, node: Node, depth: int) -> str:
        if isinstance(node, BNode):
            if self.index.is_list(node):
                return "( " + " ".join(self.value(i, depth) for i in self.index.items(node)) + " )"
            return "[" + self.predicates(node, depth) + " ]"
        return self.term(node)

    def term(self, node: Node) -> str:
        if isinstance(node, URIRef):
            iri = str(node)
            for prefix, namespace in self.prefixes:
                if iri.startswith(namespace) and _TURTLE_LOCAL.match(iri[len(namespace) :]):
                    return f"{prefix}:{iri[len(namespace) :]}"
        return node.n3()


class _XmlWriter:
    def __init__(self, index: TripleIndex, prefixes: dict[str, str]) -> None:
        self.index = index
        self.namespaces: dict[str, str] = {ns: prefix for prefix, ns in prefixes.items()}
        self.qnames: dict[Node, str] = {}
        for _, p, _ in index.triples:
            self._qname(p)

    def lines(self) -> Iterator[str]:
        yield '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF'
        for namespace, prefix in sorted(self.namespaces.items(), key=lambda n: n[1]):
            yield f"\n  xmlns:{prefix}={xml_attr(namespace)}"
        yield ">\n"
        for subject in self.index.subjects():
            yield f"  <rdf:Description rdf:about={xml_attr(str(subject))}>\n"
            yield from self._properties(subject, 2)
            yield "  </rdf:Description>\n"
        yield "</rdf:RDF>\n"

    def _properties(self, subject: Node, depth: int) -> Iterator[str]:
        pad = "  " * depth
        for p, o in self.index.pairs(subject):
            name = self.qnames[p]
            if isinstance(o, URIRef):
                yield f"{pad}<{name} rdf:resource={xml_attr(str(o))}/>\n"
            elif isinstance(o, Literal):
                attributes = ""
                if o.language:
                    attributes = f" xml:lang={xml_attr(o.language)}"
                elif o.datatype is not None:
                    attributes = f" rdf:datatype={xml_attr(str(o.datatype))}"
                yield f"{pad}<{name}{attributes}>{xml_text(str(o))}</{name}>\n"
            elif self.index.is_list(o):
                yield f'{pad}<{name} rdf:parseType="Collection">\n'
                for item in self.index.items(o):
                    yield f"{pad}  <rdf:Description rdf:about={xml_attr(str(item))}/>\n"
                yield f"{pad}</{name}>\n"
            else:
                yield f'{pad}<{name} rdf:parseType="Resource">\n'
                yield from self._properties(o, depth + 1)
                yield f"{pad}</{name}>\n"

    def _qname(self, predicate: Node) -> None:
        if predicate in self.qnames:
            return
        iri = str(predicate)
        match = _NC_NAME_TAIL.search(iri)
        if match is None or match.start() == 0:
            raise ValueError(f"the property {iri} has no XML name")
        namespace, local = iri[: match.start()], match.group()
        prefix = self.namespaces.get(namespace)
        if prefix is None:
            prefix = f"ns{len(self.namespaces) + 1}"
            self.namespaces[namespace] = prefix
        self.qnames[predicate] = f"{prefix}:{local}"


class _JsonLdWriter:
    def __init__(self, index: TripleIndex, context: dict[str, str]) -> None:
        self.index = index
        self.prefixes = sorted(context.items(), key=lambda p: -len(p[1]))

    def node(self, subject: Node) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(subject, URIRef):
            out["@id"] = self.compact(subject)
        types = [self.compact(o) for p, o in self.index.pairs(subject) if p == T.RDF_TYPE]
        if types:
            out["@type"] = types
        for p, o in self.index.pairs(subject):
            if p != T.RDF_TYPE:
                out.setdefault(self.compact(p), []).append(self.value(o))
        return out

    def value(self, node: Node) -> Any:
        if isinstance(node, URIRef):
            return {"@id": self.compact(node)}
        if isinstance(node, Literal):
            if node.language:
                return {"@value": str(node), "@language": node.language}
            if node.datatype is not None and node.datatype != T.XSD_STRING:
                return {"@value": str(node), "@type": self.compact(URIRef(node.datatype))}
            return str(node)
        if self.index.is_list(node):
            return {"@list": [self.value(i) for i in self.index.items(node)]}
        return self.node(node)

    def compact(self, node: Node) -> str:
        iri = str(node)
        for prefix, namespace in self.prefixes:
            if iri.startswith(namespace) and len(iri) > len(namespace):
                local = iri[len(namespace) :]
                if not local.startswith("//"):
                    return f"{prefix}:{local}"
        return iri
