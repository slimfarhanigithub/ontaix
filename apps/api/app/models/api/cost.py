"""`GET /cost`: agent read figures and Ontaix's own language model usage for one month."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel


class LlmPurposeUsage(ApiModel):
    purpose: Literal["teach_extraction", "concept_expansion", "document_extraction", "document_ocr"]
    calls: int = Field(ge=0)
    cost_eur: float = Field(ge=0)


class LlmUsage(ApiModel):
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    token_cap: int = Field(ge=0)
    cost_eur: float = Field(ge=0)
    by_purpose: list[LlmPurposeUsage]


class PlatformCost(ApiModel):
    platform: str
    agents_with_access: int
    cost_eur: float
    share_percent: int


class CostSummary(ApiModel):
    month: dt.date
    measured_eur: float
    allocated_eur: float
    agents_registered: int
    agents_with_access: int
    reads: int
    by_platform: list[PlatformCost]
    llm: LlmUsage
