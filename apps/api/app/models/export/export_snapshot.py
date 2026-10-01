"""The approved model of one export scope, as the export writers read it.

The export service reads the tenant's model once, keeps what the caller may read in the scope,
and hands the writers this snapshot; the writers read nothing else. The shapes are plain
dataclasses so a child process can receive them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ExportScope = Literal["company", "domain", "all"]
ExportFormat = Literal["owl", "owx", "turtle", "jsonld", "skos", "docx"]
# How a concept came from its parent: `birth` with an action, `spec` as an `is a`, or `root`.
BirthKind = Literal["birth", "spec", "root"]
# `rel` a relation with an action, `isa` a specialisation that is not a birth, `same` an
# equivalence, `clash` a conflict.
ExportRelationKind = Literal["rel", "isa", "same", "clash"]


@dataclass(frozen=True)
class ExportAttribute:
    """An approved attribute: taught when `value` is set, read from a source otherwise."""

    name: str
    type: str
    value: str | None = None
    col: str | None = None
    fill: int | None = None

    @property
    def taught(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class ExportConcept:
    """An approved concept; the company root has `birth` `root`, no domain and no parent."""

    id: uuid.UUID
    company_id: uuid.UUID
    label: str
    birth: BirthKind
    domain_key: str | None = None
    parent_id: uuid.UUID | None = None
    birth_action: str | None = None
    birth_reverse: bool = False
    rule: str | None = None
    attributes: tuple[ExportAttribute, ...] = ()


@dataclass(frozen=True)
class ExportRelation:
    """An approved relation that is not a birth, from `a` to `b`."""

    a_id: uuid.UUID
    b_id: uuid.UUID
    kind: ExportRelationKind
    action: str


@dataclass(frozen=True)
class ExportDomain:
    key: str
    name: str
    owner: str
    color: str


@dataclass(frozen=True)
class ExportCompany:
    """A company in the scope, with the keys of its domains that hold a concept of the scope."""

    id: uuid.UUID
    key: str
    name: str
    sub: str
    domain_keys: tuple[str, ...] = ()


@dataclass
class ExportSnapshot:
    """Everything an export writes. `concepts` holds the scope's concepts and every company
    root; `outside` holds concepts of readable companies that a relation of the scope names but
    that are not in the scope, referenced and never described, and `outside_companies` their
    companies."""

    scope: ExportScope
    scope_name: str
    tenant_name: str
    exported_at: datetime
    base_iri: str
    language: str
    companies: list[ExportCompany] = field(default_factory=list)
    domains: list[ExportDomain] = field(default_factory=list)
    concepts: list[ExportConcept] = field(default_factory=list)
    relations: list[ExportRelation] = field(default_factory=list)
    outside: list[ExportConcept] = field(default_factory=list)
    outside_companies: list[ExportCompany] = field(default_factory=list)
