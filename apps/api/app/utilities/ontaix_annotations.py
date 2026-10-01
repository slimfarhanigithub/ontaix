"""The `ox:` annotations of an Ontaix export, read onto the parsed items of any OWL format.

The RDF and OWL/XML readers collect every annotation assertion of the file as
`subject -> property -> values`; this module reads from them each class's birth parent
(`ox:bornFrom`), birth action and direction, domain, specialisation rule and taught attributes
(annotation assertions of properties typed by `ox:attributeType`), and marks the company root: the
class annotated `ox:company` with no `ox:domain` and no birth parent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.ontology_import.parsed_ontology import OntologyItem, TaughtValue
from app.utilities import ontaix_vocabulary as ox

RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
XSD = "http://www.w3.org/2001/XMLSchema#"
# A decimal or date value gives its type; any other value takes its property's `ox:attributeType`.
DATATYPE_TYPES = {XSD + "decimal": "number", XSD + "date": "date"}
TRUE_TEXTS = ("true", "1")

Annotations = dict[str, dict[str, list["AnnotationValue"]]]


@dataclass(frozen=True)
class AnnotationValue:
    """An annotation's value: an IRI, or a literal with its datatype or language."""

    value: str
    iri: bool = False
    datatype: str | None = None
    language: str | None = None


def apply_ontaix(items: dict[str, OntologyItem], annotations: Annotations) -> None:
    """Set the Ontaix fields of every item from the file's annotations."""
    typed = {
        prop: values for prop, values in annotations.items() if str(ox.ATTRIBUTE_TYPE) in values
    }
    for source, item in items.items():
        found = annotations.get(source, {})
        item.domain = _literal(found, ox.DOMAIN)
        item.born_from = _iri(found, ox.BORN_FROM)
        item.action = _literal(found, ox.BIRTH_ACTION)
        item.birth_reverse = (_literal(found, ox.BIRTH_REVERSE) or "").lower() in TRUE_TEXTS
        item.rule = _literal(found, ox.RULE)
        item.root = str(ox.COMPANY) in found and item.domain is None and item.born_from is None
        for prop in sorted(found):
            meta = typed.get(prop)
            if meta is None:
                continue
            name = _label(meta) or prop
            declared = _literal(meta, ox.ATTRIBUTE_TYPE) or "text"
            for value in found[prop]:
                if value.iri:
                    continue
                kind = DATATYPE_TYPES.get(value.datatype or "", declared)
                item.attributes.append(TaughtValue(name, kind, value.value))


def _literal(found: dict[str, list[AnnotationValue]], prop: object) -> str | None:
    return next((v.value for v in found.get(str(prop), []) if not v.iri), None)


def _iri(found: dict[str, list[AnnotationValue]], prop: object) -> str | None:
    return next((v.value for v in found.get(str(prop), []) if v.iri), None)


def _label(found: dict[str, list[AnnotationValue]]) -> str | None:
    values = sorted(
        (v for v in found.get(RDFS_LABEL, []) if not v.iri),
        key=lambda v: (v.language not in (None, "en"), v.language or "", v.value),
    )
    return values[0].value if values else None
