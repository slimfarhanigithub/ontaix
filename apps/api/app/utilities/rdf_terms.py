"""The RDF, RDFS, OWL, XSD and SKOS terms an export writes, each created once.

rdflib builds a new term on every namespace attribute access, which costs more than a
20,000-concept export can spend in its inner loops; the export modules use these instead.
"""

from __future__ import annotations

from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

OWL_NS = str(OWL)
RDF_NS = str(RDF)
RDFS_NS = str(RDFS)
XSD_NS = str(XSD)
SKOS_NS = str(SKOS)

OWL_ANNOTATION_PROPERTY = OWL.AnnotationProperty
OWL_CLASS = OWL.Class
OWL_DATATYPE_PROPERTY = OWL.DatatypeProperty
OWL_EQUIVALENT_CLASS = OWL.equivalentClass
OWL_NAMED_INDIVIDUAL = OWL.NamedIndividual
OWL_OBJECT_PROPERTY = OWL.ObjectProperty
OWL_ON_PROPERTY = OWL.onProperty
OWL_ONTOLOGY = OWL.Ontology
OWL_RESTRICTION = OWL.Restriction
OWL_SOME_VALUES_FROM = OWL.someValuesFrom
OWL_UNION_OF = OWL.unionOf
OWL_VERSION_INFO = OWL.versionInfo
RDF_FIRST = RDF.first
RDF_NIL = RDF.nil
RDF_OBJECT = RDF.object
RDF_PREDICATE = RDF.predicate
RDF_REST = RDF.rest
RDF_STATEMENT = RDF.Statement
RDF_SUBJECT = RDF.subject
RDF_TYPE = RDF.type
RDFS_COMMENT = RDFS.comment
RDFS_DOMAIN = RDFS.domain
RDFS_LABEL = RDFS.label
RDFS_RANGE = RDFS.range
RDFS_SUB_CLASS_OF = RDFS.subClassOf
SKOS_BROADER = SKOS.broader
SKOS_COLLECTION = SKOS.Collection
SKOS_CONCEPT = SKOS.Concept
SKOS_CONCEPT_SCHEME = SKOS.ConceptScheme
SKOS_EXACT_MATCH = SKOS.exactMatch
SKOS_HAS_TOP_CONCEPT = SKOS.hasTopConcept
SKOS_IN_SCHEME = SKOS.inScheme
SKOS_MEMBER = SKOS.member
SKOS_NOTE = SKOS.note
SKOS_PREF_LABEL = SKOS.prefLabel
SKOS_RELATED = SKOS.related
SKOS_TOP_CONCEPT_OF = SKOS.topConceptOf
XSD_ANY_URI = XSD.anyURI
XSD_DATE = XSD.date
XSD_DECIMAL = XSD.decimal
XSD_STRING = XSD.string
XSD_BOOLEAN = XSD.boolean
