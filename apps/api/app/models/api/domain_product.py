"""Domain product DTOs."""

from __future__ import annotations

import uuid

from app.models.api.base import ApiModel


class DomainProductCounts(ApiModel):
    members: int
    pending: int
    bound: int


class DomainProduct(ApiModel):
    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    name: str
    owner: str
    color: str
    revision: int
    version: str
    hidden: bool
    counts: DomainProductCounts


class DomainProductPatch(ApiModel):
    hidden: bool
