"""Proposal DTOs: the proposal itself, its artefacts and the decision results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.api.actor import Actor
from app.models.api.attribute import Attribute
from app.models.api.audit import AuditEntry
from app.models.api.base import ApiModel
from app.models.api.binding import Binding
from app.models.api.concept import Concept
from app.models.api.deletion_impact import ensure_unique_ids
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
    revision: int = Field(default=0, ge=0)
    # Open proposals in the branch of an open concept or spec proposal, itself excluded; set by
    # the reads that list proposals, absent elsewhere.
    open_below: int | None = Field(default=None, ge=0, exclude_if=lambda v: v is None)
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


class ProposalEdit(ApiModel):
    """An in-place edit of a pending draft: the revision the editor saw, and a new label
    (concept and spec) and/or action (concept birth action and relation)."""

    revision: int = Field(ge=0)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    action: str | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode="after")
    def _one_change(self) -> ProposalEdit:
        if self.label is None and self.action is None:
            raise ValueError("label or action is required")
        return self


class BulkDeleteRequest(ApiModel):
    """Concepts and domain products of one company to delete through one proposal."""

    company_id: uuid.UUID
    concept_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    domain_product_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _some_items(self) -> BulkDeleteRequest:
        ensure_unique_ids(self.concept_ids, self.domain_product_ids)
        if not self.concept_ids and not self.domain_product_ids:
            raise ValueError("conceptIds or domainProductIds is required")
        return self


class BranchResult(ApiModel):
    root_id: uuid.UUID
    approved: int = Field(ge=0)
    skipped: int = Field(ge=0)
    remaining: int = Field(ge=0)
    batches: int = Field(ge=0)
    complete: bool


class BulkResult(ApiModel):
    approved: int
    rejected: int
    rounds: int
    remaining: int
    caption: str | None = None
