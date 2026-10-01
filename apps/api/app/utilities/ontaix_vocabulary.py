"""The Ontaix annotation vocabulary (`ox:`) that exports write and ontology import reads.

Every OWL and SKOS export declares these terms; ontology import reads them back so an OWL
export of a company imports into the same model.
"""

from __future__ import annotations

from rdflib import Namespace

OX_NS = "https://ontaix.dev/ns#"
OX = Namespace(OX_NS)

COMPANY = OX.company
DOMAIN = OX.domain
BORN_FROM = OX.bornFrom
BIRTH_ACTION = OX.birthAction
BIRTH_REVERSE = OX.birthReverse
ACTION = OX.action
ATTRIBUTE_VALUE = OX.attributeValue
ATTRIBUTE_TYPE = OX.attributeType
COLUMN = OX.column
FILL = OX.fill
RULE = OX.rule
KEY = OX.key
COLOR = OX.color
OWNER = OX.owner
CONFLICTS_WITH = OX.conflictsWith

COMPANY_CLASS = OX.Company
DOMAIN_CLASS = OX.Domain

ANNOTATION_PROPERTIES = (
    COMPANY,
    DOMAIN,
    BORN_FROM,
    BIRTH_ACTION,
    BIRTH_REVERSE,
    ACTION,
    ATTRIBUTE_VALUE,
    ATTRIBUTE_TYPE,
    COLUMN,
    FILL,
    RULE,
    KEY,
    COLOR,
    OWNER,
    CONFLICTS_WITH,
)
CLASSES = (COMPANY_CLASS, DOMAIN_CLASS)

# Taught attribute types and the XSD datatype of their values.
TAUGHT_TYPES = ("text", "number", "date")


def is_ontaix_term(iri: str) -> bool:
    return iri.startswith(OX_NS)
