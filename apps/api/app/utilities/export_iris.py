"""The IRIs of an export: stable across exports, made from company keys and concept ids.

A company is `<base><companyKey>`, a concept `<base><companyKey>/c/<conceptId>`, a relation's
property `<base><companyKey>/p/<slug of the action>`, a taught attribute's property
`<base><companyKey>/a/<slug of the name>`, and an attribute read from a source, whose property
belongs to one class, `<base><companyKey>/c/<conceptId>/a/<slug of the name>`. A tenant domain
is `<base>domain/<key>` and the export itself `<base>export/<scope>/<date>`. No tenant name and
no user appears in an IRI.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from rdflib import URIRef

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Lower-case ASCII letters and digits, every other run one dash; `x` when nothing is left."""
    return _NON_ALNUM.sub("-", text.lower()).strip("-") or "x"


def company_iri(base: str, company_key: str) -> URIRef:
    return URIRef(f"{base}{company_key}")


def concept_iri(base: str, company_key: str, concept_id: uuid.UUID) -> URIRef:
    return URIRef(f"{base}{company_key}/c/{concept_id}")


def property_iri(base: str, company_key: str, action_slug: str) -> URIRef:
    return URIRef(f"{base}{company_key}/p/{action_slug}")


def taught_attribute_iri(base: str, company_key: str, name_slug: str) -> URIRef:
    return URIRef(f"{base}{company_key}/a/{name_slug}")


def source_attribute_iri(
    base: str, company_key: str, concept_id: uuid.UUID, name_slug: str
) -> URIRef:
    return URIRef(f"{base}{company_key}/c/{concept_id}/a/{name_slug}")


def domain_iri(base: str, key: str) -> URIRef:
    return URIRef(f"{base}domain/{key}")


def ontology_iri(base: str, scope: str, exported_at: datetime) -> URIRef:
    return URIRef(f"{base}export/{scope}/{exported_at.date().isoformat()}")
