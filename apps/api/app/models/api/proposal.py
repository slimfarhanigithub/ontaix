"""Proposal DTOs: the proposal itself, its artefacts and the decision results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.actor import Actor
from app.models.api.attribute import Attribute
from app.models.api.audit import AuditEntry
from app.models.api.base import ApiModel
from app.models.api.binding import Binding
from app.models.api.concept import Concept
from app.models.api.domain_product import DomainProduct
from app.models.api.origin import Origin, OriginDetail
from app.models.api.relation import Relation


class Approval(ApiModel):
    ordinal: int
    user_id: uuid.UUID
    user_name: str | None = None
    approved_at: datetime


class Artefacts(ApiModel):
    concepts: list[Concept] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    bindings: list[Binding] = Field(default_factory=list)
    attributes: list[Attribute] = Field(default_factory=list)
    domain_products: list[DomainProduct] = Field(default_factory=list)
    companies: list[dict] = Field(default_factory=list)


class Proposal(ApiModel):
    id: uuid.UUID
    type: Literal["concept", "spec", "relation", "source", "bind", "attr", "change"]
    change_kind: str | None = None
    state: Literal["pending", "half_approved", "approved", "rejected"]
    title: str
    heading: str
    color: str
    company_id: uuid.UUID | None = None
    domain_product_id: uuid.UUID | None = None
    parent_label: str | None = None
    deps: list[str]
    ready: bool
    wait_for: str | None = None
    html: str
    why: str | None = None
    caption: str | None = None
    concept_id: uuid.UUID | None = None
    relation_id: uuid.UUID | None = None
    relation_ids: list[uuid.UUID] = Field(default_factory=list)
    source_id: uuid.UUID | None = None
    binding_ids: list[uuid.UUID] = Field(default_factory=list)
    attribute_id: uuid.UUID | None = None
    proposer: Actor
    origin: Origin
    origin_detail: OriginDetail | None
    approvals: list[Approval] = Field(default_factory=list)
    bulk: bool = False
    created_at: datetime
    decided_at: datetime | None = None
    artefacts: Artefacts | None = None


class DecisionResult(ApiModel):
    proposal: Proposal
    artefacts: Artefacts
    cascaded: list[Proposal]
    audit: AuditEntry | None = None
    caption: str | None = None


class RejectRequest(ApiModel):
    reason: str | None = Field(default=None, max_length=500)


class BulkResult(ApiModel):
    approved: int
    rejected: int
    rounds: int
    remaining: int
    caption: str | None = None
