"""Company DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.concept import Concept
from app.models.api.domain_product import DomainProduct
from app.models.api.proposal import Proposal


class CompanyCounts(ApiModel):
    concepts: int
    sources: int
    equivalences: int
    bound: int
    percent_bound: int
    domains_with_cells: int


class Company(ApiModel):
    id: uuid.UUID
    key: str
    name: str
    sub: str
    position: int
    is_home: bool
    root_id: uuid.UUID
    domain_products: list[DomainProduct]
    counts: CompanyCounts
    dying_at: datetime | None = None


class CompanyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    sub: str = Field(default="", max_length=200)
    start: Literal["starter_vocabulary", "one_cell"]


class CompanyCreated(ApiModel):
    company: Company
    root: Concept
    proposals: list[Proposal]
