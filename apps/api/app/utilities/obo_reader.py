"""OBO flat files read as terms, relations and their names.

`[Term]` stanzas give terms (`id`, `name`, `is_a`, `relationship`), `[Typedef]` stanzas give
the names of relations, and `[Instance]` stanzas individuals typed by `instance_of`. Trailing
`! comments` and `{qualifiers}` are dropped. `import:` header lines are reported and never
fetched; `equivalent_to`, `intersection_of`, `union_of` and `disjoint_from` are reported, never
reasoned over.
"""

from __future__ import annotations

import re

from app.models.ontology_import.parsed_ontology import (
    OBO_NAME,
    LabelLiteral,
    OntologyItem,
    OntologyProperty,
    OntologyStatement,
    ParsedOntology,
    SkippedSource,
    SkipReason,
)
from app.utilities.document_text import decode_text

_STANZA = re.compile(r"^\[(\w+)\]$")
_TAG = re.compile(r"^([A-Za-z_-]+):\s?(.*)$")
_TRAILING = re.compile(r"\s*(\{[^}]*\})?\s*(!.*)?$")
UNSUPPORTED_TAGS = ("intersection_of", "union_of", "disjoint_from")


def read_obo(data: bytes) -> ParsedOntology:
    parsed = ParsedOntology(format="obo")
    stanzas: list[tuple[str, list[tuple[str, str]]]] = [("header", [])]
    for raw in decode_text(data).splitlines():
        line = raw.strip()
        if not line or line.startswith("!"):
            continue
        stanza = _STANZA.match(line)
        if stanza:
            stanzas.append((stanza.group(1), []))
            continue
        tag = _TAG.match(line)
        if tag:
            stanzas[-1][1].append((tag.group(1), _value(tag.group(2))))
    items: dict[str, OntologyItem] = {}
    relationships: list[tuple[str, str, str]] = []
    for kind, tags in stanzas:
        if kind == "header":
            for name, value in tags:
                if name == "import" and value:
                    _skip(parsed, value, "remote_import_not_fetched")
        elif kind in ("Term", "Instance"):
            _term(parsed, items, relationships, tags, individual=kind == "Instance")
        elif kind == "Typedef":
            _typedef(parsed, tags)
    for term, prop, target in relationships:
        if target in items:
            parsed.properties.setdefault(prop, OntologyProperty(source=prop, local_name=prop))
            parsed.statements.append(OntologyStatement(term, prop, target))
    known = set(items)
    for item in items.values():
        item.parents = [(p, k) for p, k in item.parents if p in known and p != item.source]
    parsed.items = sorted(items.values(), key=lambda i: i.source)
    return parsed


def _term(
    parsed: ParsedOntology,
    items: dict[str, OntologyItem],
    relationships: list[tuple[str, str, str]],
    tags: list[tuple[str, str]],
    individual: bool,
) -> None:
    term_id = next((v for n, v in tags if n == "id"), "")
    if not term_id:
        return
    item = items.setdefault(
        term_id, OntologyItem(source=term_id, individual=individual, local_name=term_id)
    )
    for name, value in tags:
        if name == "name" and value:
            item.add_label(OBO_NAME, LabelLiteral(value))
        elif name == "is_a" and value:
            item.parents.append((value.split()[0], "spec"))
        elif name == "instance_of" and value:
            item.parents.append((value.split()[0], "instance"))
        elif name == "relationship":
            parts = value.split()
            if len(parts) >= 2:
                relationships.append((term_id, parts[0], parts[1]))
        elif name == "equivalent_to":
            _skip(parsed, term_id, "equivalence_not_imported")
        elif name in UNSUPPORTED_TAGS:
            _skip(parsed, term_id, "unsupported_axiom")


def _typedef(parsed: ParsedOntology, tags: list[tuple[str, str]]) -> None:
    prop_id = next((v for n, v in tags if n == "id"), "")
    if not prop_id:
        return
    entry = parsed.properties.setdefault(
        prop_id, OntologyProperty(source=prop_id, local_name=prop_id)
    )
    for name, value in tags:
        if name == "name" and value:
            entry.add_label(OBO_NAME, LabelLiteral(value))
        elif name == "holds_over_chain":
            _skip(parsed, prop_id, "unsupported_axiom")


def _value(raw: str) -> str:
    """A tag value without its trailing qualifiers and comment."""
    return _TRAILING.sub("", raw).strip()


def _skip(parsed: ParsedOntology, source: str, reason: SkipReason) -> None:
    entry = SkippedSource(source, reason)
    if entry not in parsed.skipped:
        parsed.skipped.append(entry)
