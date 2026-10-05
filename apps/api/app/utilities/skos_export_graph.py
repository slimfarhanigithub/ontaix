"""The SKOS graph of an export snapshot, for thesaurus tools, as a list of triples.

One `skos:ConceptScheme` per company (the company IRI, `skos:prefLabel` its name); each concept a
`skos:Concept` with `skos:prefLabel` and `skos:inScheme`, `skos:broader` its birth or
specialisation parent, `skos:topConceptOf` its scheme when the parent is the company root.
Relations are `skos:related` with a reified statement carrying `ox:action`; equivalences
`skos:exactMatch`; each tenant domain a `skos:Collection` with its concepts as `skos:member`;
taught attributes `skos:note` `<name>: <value>`. SKOS carries the tree; it does not round-trip
actions exactly.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from rdflib import BNode, Literal, URIRef

from app.models.export.export_snapshot import ExportConcept, ExportSnapshot
from app.utilities import ontaix_vocabulary as ox
from app.utilities import rdf_terms as T
from app.utilities.export_iris import company_iri, concept_iri, domain_iri, ontology_iri
from app.utilities.owl_export_graph import TripleList
from app.utilities.triple_index import Triple


def skos_triples(snapshot: ExportSnapshot) -> list[Triple]:
    s = snapshot
    g = TripleList()
    base, lang = s.base_iri, s.language
    keys = {c.id: c.key for c in [*s.outside_companies, *s.companies]}
    by_id: dict[uuid.UUID, ExportConcept] = {c.id: c for c in [*s.outside, *s.concepts]}

    def iri(concept_id: uuid.UUID) -> URIRef:
        concept = by_id[concept_id]
        return concept_iri(base, keys[concept.company_id], concept.id)

    ontology = ontology_iri(base, s.scope, s.exported_at)
    g.add((ontology, T.RDF_TYPE, T.OWL_ONTOLOGY))
    g.add(
        (
            ontology,
            T.SKOS_PREF_LABEL,
            Literal(f"Ontology Builder export · {s.scope_name}", lang=lang),
        )
    )
    g.add((ox.ACTION, T.RDF_TYPE, T.OWL_ANNOTATION_PROPERTY))
    for company in s.companies:
        scheme = company_iri(base, company.key)
        g.add((scheme, T.RDF_TYPE, T.SKOS_CONCEPT_SCHEME))
        g.add((scheme, T.SKOS_PREF_LABEL, Literal(company.name, lang=lang)))
    roots = {c.id for c in s.concepts if c.birth == "root"}
    members: dict[str, list[URIRef]] = defaultdict(list)
    for concept in s.concepts:
        if concept.birth == "root":
            continue
        node = iri(concept.id)
        scheme = company_iri(base, keys[concept.company_id])
        g.add((node, T.RDF_TYPE, T.SKOS_CONCEPT))
        g.add((node, T.SKOS_PREF_LABEL, Literal(concept.label, lang=lang)))
        g.add((node, T.SKOS_IN_SCHEME, scheme))
        if concept.parent_id in roots:
            g.add((node, T.SKOS_TOP_CONCEPT_OF, scheme))
            g.add((scheme, T.SKOS_HAS_TOP_CONCEPT, node))
        elif concept.parent_id is not None:
            g.add((node, T.SKOS_BROADER, iri(concept.parent_id)))
        if concept.domain_key is not None:
            members[concept.domain_key].append(node)
        for attribute in concept.attributes:
            if attribute.taught:
                g.add(
                    (node, T.SKOS_NOTE, Literal(f"{attribute.name}: {attribute.value}", lang=lang))
                )
    for domain in s.domains:
        collection = domain_iri(base, domain.key)
        g.add((collection, T.RDF_TYPE, T.SKOS_COLLECTION))
        g.add((collection, T.SKOS_PREF_LABEL, Literal(domain.name, lang=lang)))
        for node in members.get(domain.key, []):
            g.add((collection, T.SKOS_MEMBER, node))
    statements = 0
    for relation in s.relations:
        if relation.a_id in roots or relation.b_id in roots:
            continue
        a, b = iri(relation.a_id), iri(relation.b_id)
        if relation.kind == "same":
            g.add((a, T.SKOS_EXACT_MATCH, b))
        elif relation.kind in ("rel", "isa"):
            g.add((a, T.SKOS_RELATED, b))
            statements += 1
            statement = BNode(f"s{statements}")
            g.add((statement, T.RDF_TYPE, T.RDF_STATEMENT))
            g.add((statement, T.RDF_SUBJECT, a))
            g.add((statement, T.RDF_PREDICATE, T.SKOS_RELATED))
            g.add((statement, T.RDF_OBJECT, b))
            g.add((statement, ox.ACTION, Literal(relation.action)))
    return list(dict.fromkeys(g))
