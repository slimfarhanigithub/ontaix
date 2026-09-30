"""Tenant settings and appearance DTOs as they appear in the scene snapshot."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel

DEFAULT_LLM_MONTHLY_TOKEN_CAP = 2_000_000
DEFAULT_OCR_MONTHLY_PAGE_CAP = 1000


class Settings(ApiModel):
    # Set by a super admin; read-only here. `single` keeps `multi_company` off.
    company_mode: Literal["single", "multiple"]
    voice: bool
    import_docs: bool
    live_teaching: bool
    everyone_teaches: bool
    approval_required: Literal[True]
    two_approvers: bool
    auto_attrs: bool
    notify_owners: bool
    multi_company: bool
    cross_company: bool
    animations: bool
    coverage_default: bool
    legend: bool
    read_only_connectors: Literal[True]
    refresh: Literal["5 min", "15 min", "1 h", "daily"]
    agent_access: bool
    cost_cap: bool
    llm_monthly_token_cap: int = Field(ge=0, le=1_000_000_000)
    ocr_monthly_page_cap: int = Field(ge=0, le=1_000_000)
    egress_allowlist: list[str] = Field(default_factory=list)


class AppearanceDefaults(ApiModel):
    colors: dict[str, str]
    accent: str
    source: str


class Appearance(ApiModel):
    theme: Literal["dark", "light"]
    colors: dict[str, str]
    accent: str
    source: str
    defaults: AppearanceDefaults
