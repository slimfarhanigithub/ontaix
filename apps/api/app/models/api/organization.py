"""Organizations as the platform portal reads and writes them (a tenant is an organization)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel

CompanyModeName = Literal["single", "multiple"]


class OrganizationRef(ApiModel):
    id: uuid.UUID
    name: str
    slug: str


class Organization(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    company_mode: CompanyModeName
    status: Literal["active", "disabled"]
    companies: int
    users: int
    created_at: datetime
    disabled_at: datetime | None = None


class OrganizationCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    company_mode: CompanyModeName


class OrganizationUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    company_mode: CompanyModeName | None = None
