"""A list of RDF triples indexed by subject, for writing an export in one pass.

Export graphs are written from a plain list of rdflib terms rather than an rdflib store: a store
indexes every triple three ways, which costs more time and memory than a 20,000-concept export
can spend. Blank nodes in an export are referenced once (restrictions, unions and list cells),
so writers inline them where they are used.
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef

from app.utilities import rdf_terms as T

Node = URIRef | BNode | Literal
Triple = tuple[Node, Node, Node]


class TripleIndex:
    def __init__(self, triples: list[Triple]) -> None:
        self.triples = triples
        self.out: dict[Node, list[tuple[Node, Node]]] = {}
        for s, p, o in triples:
            self.out.setdefault(s, []).append((p, o))

    def subjects(self) -> list[URIRef]:
        """Named subjects in first-seen order."""
        return [s for s in self.out if isinstance(s, URIRef)]

    def pairs(self, subject: Node) -> list[tuple[Node, Node]]:
        return self.out.get(subject, [])

    def value(self, subject: Node, predicate: Node) -> Node | None:
        return next((o for p, o in self.pairs(subject) if p == predicate), None)

    def objects(self, subject: Node, predicate: Node) -> list[Node]:
        return [o for p, o in self.pairs(subject) if p == predicate]

    def is_list(self, node: Node) -> bool:
        return isinstance(node, BNode) and self.value(node, T.RDF_FIRST) is not None

    def items(self, head: Node) -> list[Node]:
        """The members of an RDF list, from its first cell to `rdf:nil`."""
        members: list[Node] = []
        cell: Node | None = head
        while cell is not None and cell != T.RDF_NIL:
            first = self.value(cell, T.RDF_FIRST)
            if first is None:
                break
            members.append(first)
            cell = self.value(cell, T.RDF_REST)
        return members
