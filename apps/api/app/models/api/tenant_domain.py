"""Tenant domain DTOs: the domain as `GET /domains` lists it, and the bodies that propose one."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.models.api.base import ApiModel
from app.models.api.drafts import DOMAIN_KEY_PATTERN, HEX_PATTERN


class TenantDomain(ApiModel):
    key: str = Field(pattern=DOMAIN_KEY_PATTERN)
    name: str = Field(max_length=60)
    owner: str = Field(max_length=60)
    color: str = Field(pattern=HEX_PATTERN)
    default_color: str = Field(pattern=HEX_PATTERN)
    template: bool
    position: int = Field(ge=0, le=63)
    revision: int = Field(ge=0)


class DomainInput(ApiModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(pattern=HEX_PATTERN)
    owner: str = Field(default="", max_length=60)


class DomainPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=HEX_PATTERN)
    owner: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _one_change(self) -> DomainPatch:
        if self.name is None and self.color is None and self.owner is None:
            raise ValueError("at least one of name, color or owner is required")
        return self
