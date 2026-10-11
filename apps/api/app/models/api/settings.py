"""Tenant settings and appearance DTOs: the scene snapshot shapes, the patches that change them,
and the companies-may-interact impact and outcome."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.models.api.audit import AuditEntry
from app.models.api.base import ApiModel
from app.models.api.drafts import HEX_PATTERN
from app.models.api.proposal import Proposal

DEFAULT_LLM_MONTHLY_TOKEN_CAP = 2_000_000
DEFAULT_OCR_MONTHLY_PAGE_CAP = 1000
MAX_EGRESS_HOSTS = 200
MAX_EGRESS_HOST_LENGTH = 300
MAX_IMPACT_SAMPLES = 6

RefreshIntervalName = Literal["5 min", "15 min", "1 h", "daily"]
Hex = Annotated[str, Field(pattern=HEX_PATTERN)]
EgressHost = Annotated[str, Field(max_length=MAX_EGRESS_HOST_LENGTH)]


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
    company_creation: bool
    cross_company: bool
    animations: bool
    coverage_default: bool
    legend: bool
    read_only_connectors: Literal[True]
    refresh: RefreshIntervalName
    agent_access: bool
    cost_cap: bool
    llm_monthly_token_cap: int = Field(ge=0, le=1_000_000_000)
    ocr_monthly_page_cap: int = Field(ge=0, le=1_000_000)
    egress_allowlist: list[str] = Field(default_factory=list)


class SettingsPatch(ApiModel):
    """The settings an Administrator changes. The two locked settings are accepted here so
    that naming them answers `409 locked_setting` rather than a validation error."""

    voice: bool | None = None
    import_docs: bool | None = None
    live_teaching: bool | None = None
    everyone_teaches: bool | None = None
    approval_required: bool | None = None
    two_approvers: bool | None = None
    auto_attrs: bool | None = None
    notify_owners: bool | None = None
    multi_company: bool | None = None
    company_creation: bool | None = None
    cross_company: bool | None = None
    animations: bool | None = None
    coverage_default: bool | None = None
    legend: bool | None = None
    read_only_connectors: bool | None = None
    refresh: RefreshIntervalName | None = None
    agent_access: bool | None = None
    cost_cap: bool | None = None
    llm_monthly_token_cap: int | None = Field(default=None, ge=0, le=1_000_000_000)
    ocr_monthly_page_cap: int | None = Field(default=None, ge=0, le=1_000_000)
    egress_allowlist: list[EgressHost] | None = Field(default=None, max_length=MAX_EGRESS_HOSTS)

    @model_validator(mode="after")
    def _at_least_one(self) -> SettingsPatch:
        if not self.model_fields_set:
            raise ValueError("at least one setting is required")
        return self


class CrossCompanyDisable(ApiModel):
    confirmation: str = Field(max_length=100)


class CrossCompanyPair(ApiModel):
    company_a: str
    company_b: str
    count: int


class CrossCompanyImpact(ApiModel):
    relations: int
    pending_proposals: int
    pairs: list[CrossCompanyPair]
    samples: list[str] = Field(max_length=MAX_IMPACT_SAMPLES)


class CrossCompanyDisabled(ApiModel):
    removed_relations: int
    rejected_proposals: int
    proposal: Proposal
    audit: AuditEntry
    settings: Settings


class AppearanceDefaults(ApiModel):
    colors: dict[str, str]
    accent: str
    source: str


class Appearance(ApiModel):
    colors: dict[str, str]
    accent: str
    source: str
    defaults: AppearanceDefaults


class AppearancePatch(ApiModel):
    """Colour overrides per domain key, the accent and the source colour; every value a
    lower-case six-digit hex."""

    colors: dict[str, Hex] | None = None
    accent: Hex | None = None
    source: Hex | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> AppearancePatch:
        if not self.model_fields_set:
            raise ValueError("at least one of colors, accent or source is required")
        return self
