"""Whole-document extraction jobs: the job, its result and the requests that start and submit it.

The job carries progress counts only, never labels, so it is also the `extraction.changed`
payload.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.models.api.base import ApiModel
from app.models.api.teach import SourceSpan

JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JobPhase = Literal["outline", "sections", "mapping"]
FailureReason = Literal[
    "not_configured",
    "budget_exhausted",
    "rate_limited",
    "job_timeout",
    "no_drafts",
    "import_expired",
    "too_many_attempts",
    "internal",
]
Role = Literal["domain_area", "process", "subprocess", "step", "entity", "group"]
UnresolvedReason = Literal[
    "not_understood",
    "ambiguous_reference",
    "not_a_statement",
    "low_confidence",
    "ungrounded_label",
    "unknown_parent",
    "model_invalid_output",
    "timeout",
    "provider_error",
    "refused",
    "budget_exhausted",
    "node_ceiling",
    "cancelled",
]


class ExtractionStart(ApiModel):
    company_id: uuid.UUID


class DocumentExtraction(ApiModel):
    id: uuid.UUID
    import_id: uuid.UUID | None
    company_id: uuid.UUID
    state: JobState
    phase: JobPhase | None
    chunks: int = Field(ge=0)
    outline_chunks_done: int = Field(ge=0)
    section_chunks_done: int = Field(ge=0)
    outline_nodes: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    token_ceiling: int = Field(ge=1)
    node_ceiling: int = Field(ge=1)
    draft_count: int = Field(ge=0)
    degraded: bool
    failure_reason: FailureReason | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None
    submitted_at: datetime | None


class OutlineNode(ApiModel):
    index: int = Field(ge=0)
    parent_index: int | None = Field(ge=0)
    parent_concept_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None
    label: str = Field(min_length=1, max_length=120)
    role: Role
    depth: int = Field(ge=1)
    sentence_index: int = Field(ge=0, le=1999)


class DocumentDraftNote(ApiModel):
    pass_: Literal["outline", "section"] = Field(alias="pass")
    confidence: float = Field(ge=0.4, le=1)
    explanation: str | None = Field(default=None, max_length=120, exclude_if=lambda v: v is None)
    role: Role | None = Field(default=None, exclude_if=lambda v: v is None)
    depth: int | None = Field(ge=1)
    requires: list[int] = Field(max_length=2)
    sentence_index: int = Field(ge=0, le=1999)
    source_span: SourceSpan | None = Field(default=None, exclude_if=lambda v: v is None)


class ExtractionUnresolved(ApiModel):
    chunk: int | None = Field(default=None, ge=0, exclude_if=lambda v: v is None)
    sentence_index: int | None = Field(default=None, ge=0, le=1999, exclude_if=lambda v: v is None)
    label: str | None = Field(default=None, max_length=120, exclude_if=lambda v: v is None)
    reason: UnresolvedReason


class DocumentExtractionResult(ApiModel):
    extraction_id: uuid.UUID
    outline: list[OutlineNode] = Field(max_length=5000)
    drafts: list[dict[str, Any]] = Field(max_length=5000)
    notes: list[DocumentDraftNote] = Field(max_length=5000)
    unresolved: list[ExtractionUnresolved] = Field(max_length=5000)


class ExtractionSelection(ApiModel):
    """0-based indexes into a job's drafts; proposals follow draft order."""

    indexes: list[int] = Field(min_length=1, max_length=5000)

    @field_validator("indexes")
    @classmethod
    def _distinct_in_range(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("indexes must be distinct")
        if any(i < 0 or i > 4999 for i in value):
            raise ValueError("indexes lie between 0 and 4999")
        return value
