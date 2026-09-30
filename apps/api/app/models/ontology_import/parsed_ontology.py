"""The format-neutral content of an ontology or hierarchy file, as its readers hand it over.

Every reader (RDF, OWL/XML, OBO, CSV and XLSX hierarchies) produces one `ParsedOntology`; the
mapping to proposal drafts reads nothing else. Only asserted statements are kept, never an
inference. The shapes are plain dataclasses so a child process can return them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OntologyFormat = Literal[
    "rdf_xml", "turtle", "owl_xml", "json_ld", "n_triples", "obo", "csv", "xlsx"
]

# Label properties in their order of preference.
PREF_LABEL = "prefLabel"
RDFS_LABEL = "label"
ALT_LABEL = "altLabel"
OBO_NAME = "name"
LABEL_PROPERTIES = (PREF_LABEL, RDFS_LABEL, ALT_LABEL, OBO_NAME)

# How an item hangs under a named parent: `spec` for `rdfs:subClassOf` and OBO `is_a`,
# `includes` for `skos:broader` and hierarchy rows, `instance` for an individual's class.
ParentKind = Literal["spec", "includes", "instance"]

SkipReason = Literal[
    "already_known",
    "reused_existing",
    "invalid_label",
    "duplicate_label",
    "remote_import_not_fetched",
    "unsupported_axiom",
    "equivalence_not_imported",
    "datatype_property",
    "individual_skipped",
    "forbidden_action",
    "cycle",
    "unknown_parent",
    "unknown_domain",
]


@dataclass(frozen=True)
class LabelLiteral:
    text: str
    language: str | None = None


@dataclass(frozen=True)
class TaughtValue:
    """A taught attribute read from an Ontaix export: its name, type and value."""

    name: str
    type: str
    value: str


@dataclass
class OntologyItem:
    """A named class, SKOS concept, OBO term, individual or hierarchy row.

    `source` is its IRI, OBO id or `row <n>`; `labels` maps a label property to its literals in
    file order; `local_name` is the IRI's last segment, the fallback label. `parents` are the
    sources of named parents with how the item hangs under each; `action` and `domain` come
    from a hierarchy row's columns or from the `ox:` annotations of an Ontaix export, which also
    give `born_from` (the birth parent), `birth_reverse`, `rule`, `attributes`, and `root` for
    the company root.
    """

    source: str
    individual: bool = False
    labels: dict[str, list[LabelLiteral]] = field(default_factory=dict)
    local_name: str = ""
    parents: list[tuple[str, ParentKind]] = field(default_factory=list)
    action: str | None = None
    domain: str | None = None
    born_from: str | None = None
    birth_reverse: bool = False
    rule: str | None = None
    root: bool = False
    attributes: list[TaughtValue] = field(default_factory=list)

    def add_label(self, prop: str, literal: LabelLiteral) -> None:
        self.labels.setdefault(prop, []).append(literal)


@dataclass
class OntologyProperty:
    """A named object property: its labels, local name, and named domains and ranges."""

    source: str
    labels: dict[str, list[LabelLiteral]] = field(default_factory=dict)
    local_name: str = ""
    domains: list[str] = field(default_factory=list)
    ranges: list[str] = field(default_factory=list)

    def add_label(self, prop: str, literal: LabelLiteral) -> None:
        self.labels.setdefault(prop, []).append(literal)


@dataclass(frozen=True)
class OntologyStatement:
    """`subject <property> object` from a some or all restriction or an OBO relationship."""

    subject: str
    property: str
    object: str


@dataclass(frozen=True)
class SkippedSource:
    source: str
    reason: SkipReason
    label: str | None = None


@dataclass
class ParsedOntology:
    format: OntologyFormat
    items: list[OntologyItem] = field(default_factory=list)
    properties: dict[str, OntologyProperty] = field(default_factory=dict)
    statements: list[OntologyStatement] = field(default_factory=list)
    skipped: list[SkippedSource] = field(default_factory=list)
    # True for CSV and XLSX hierarchies: items keep file order instead of the source-sorted one.
    table: bool = False
    # True when the file uses the Ontaix vocabulary (`ox:`), as an Ontaix export does.
    ontaix: bool = False
