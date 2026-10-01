"""Deletion impact DTOs: what a deletion targets and what approving it would remove."""

from __future__ import annotations

import uuid

from pydantic import Field, model_validator

from app.models.api.base import ApiModel

MAX_BULK_CONCEPTS = 200
MAX_BULK_DOMAIN_PRODUCTS = 20
MAX_IMPACT_NAMES = 6


def ensure_unique_ids(
    concept_ids: list[uuid.UUID] | None, domain_product_ids: list[uuid.UUID] | None
) -> None:
    """Each list names an id once (`uniqueItems`)."""
    for name, ids in (("conceptIds", concept_ids), ("domainProductIds", domain_product_ids)):
        if ids is not None and len(set(ids)) != len(ids):
            raise ValueError(f"{name} holds an id twice")


class DeletionTarget(ApiModel):
    """A whole company (`whole_company` alone), or concepts and domain products of one company."""

    company_id: uuid.UUID
    whole_company: bool = False
    concept_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_BULK_CONCEPTS)
    domain_product_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=MAX_BULK_DOMAIN_PRODUCTS
    )

    @model_validator(mode="after")
    def _one_shape(self) -> DeletionTarget:
        ensure_unique_ids(self.concept_ids, self.domain_product_ids)
        if self.whole_company:
            if self.concept_ids or self.domain_product_ids:
                raise ValueError("wholeCompany takes no conceptIds or domainProductIds")
        elif not self.concept_ids and not self.domain_product_ids:
            raise ValueError("conceptIds or domainProductIds is required")
        return self


class DeletionImpact(ApiModel):
    concepts: int = Field(ge=0)
    descendants: int = Field(ge=0)
    relations: int = Field(ge=0)
    cross_company_relations: int = Field(ge=0)
    bindings: int = Field(ge=0)
    attributes: int = Field(ge=0)
    sources: int = Field(ge=0)
    cascaded_proposals: int = Field(ge=0)
    names: list[str] = Field(default_factory=list, max_length=MAX_IMPACT_NAMES)
