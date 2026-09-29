"""Request and response of `POST /concepts/{conceptId}/expand` and the submit that follows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.models.api.base import ApiModel
from app.utilities.action_text import has_refused_character

ExpansionOutcome = Literal[
    "used",
    "not_configured",
    "rate_limited",
    "budget_exhausted",
    "timeout",
    "provider_error",
    "refused",
    "invalid_output",
]
SkipReason = Literal[
    "existing_label",
    "duplicate_in_response",
    "low_confidence",
    "over_cap",
    "parent_skipped",
    "duplicate_relation",
]


class ExpansionRequest(ApiModel):
    """`depth` and `max_children` steer the model and are enforced only when set; neither has a
    maximum."""

    depth: int | None = Field(default=None, ge=1)
    max_children: int | None = Field(default=None, ge=1)
    focus: str | None = Field(default=None, min_length=1, max_length=200)
    session_id: uuid.UUID | None = None

    @field_validator("focus")
    @classmethod
    def _plain_focus(cls, value: str | None) -> str | None:
        if value is not None and has_refused_character(value):
            raise ValueError("focus refuses markup, control and format characters")
        return value


class ExpansionNote(ApiModel):
    confidence: float = Field(ge=0.4, le=1)
    rationale: str = Field(min_length=1, max_length=120)
    depth: int | None = Field(ge=1)
    requires: list[int] = Field(max_length=2)


class ExpansionSkip(ApiModel):
    label: str = Field(min_length=1, max_length=130)
    reason: SkipReason


class ExpansionResult(ApiModel):
    """`drafts` are `ConceptDraft`s then `RelationDraft`s in the contract's draft shape; `notes`
    has one entry per draft, in the same order."""

    expansion_id: uuid.UUID | None
    expires_at: datetime | None
    concept_id: uuid.UUID
    llm_outcome: ExpansionOutcome
    degraded: bool
    drafts: list[dict[str, Any]] = Field(max_length=2000)
    notes: list[ExpansionNote] = Field(max_length=2000)
    skipped: list[ExpansionSkip] = Field(max_length=4000)


class ExpansionSelection(ApiModel):
    """0-based indexes into a stored expansion's drafts; proposals follow draft order."""

    indexes: list[int] = Field(min_length=1, max_length=2000)

    @field_validator("indexes")
    @classmethod
    def _distinct_in_range(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("indexes must be distinct")
        if any(i < 0 or i > 1999 for i in value):
            raise ValueError("indexes lie between 0 and 1999")
        return value
