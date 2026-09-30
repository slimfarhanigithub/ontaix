"""Request and response of `POST /teach/parse`."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field, model_validator

from app.models.api.base import ApiModel
from app.models.api.origin import ImportRef, InputOrigin, Origin, OriginDetail


class TeachRequest(ApiModel):
    """Typed text or a speech transcript in `text`, or a stored import sentence in
    `import_ref`; exactly one of the two."""

    company_id: uuid.UUID
    # A typed sentence holds at most 400 characters, a speech transcript at most 4,000.
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    session_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_source(self) -> TeachRequest:
        if (self.text is None) == (self.import_ref is None):
            raise ValueError("exactly one of text or importRef is required")
        if self.text is not None and self.origin != "speech" and len(self.text) > 400:
            raise ValueError("typed text holds at most 400 characters")
        return self


class Intent(ApiModel):
    """A `rel` or `spec` fact between two concepts, or an `attr` fact about one concept: the
    subject is the concept, the predicate the attribute name and the object the value."""

    kind: Literal["spec", "rel", "attr"]
    subject: str
    predicate: str | None = Field(default=None, exclude_if=lambda v: v is None)
    object: str
    rule: str | None = Field(default=None, exclude_if=lambda v: v is None)
    subject_resolved: uuid.UUID | None
    object_resolved: uuid.UUID | None


Extractor = Literal["rules", "llm", "rules+llm"]
LlmOutcome = Literal[
    "not_triggered",
    "used",
    "not_configured",
    "rate_limited",
    "budget_exhausted",
    "timeout",
    "provider_error",
    "invalid_output",
]
UnresolvedReason = Literal[
    "not_understood",
    "ambiguous_reference",
    "low_confidence",
    "model_unavailable",
    "model_invalid_output",
    "too_many_drafts",
    "not_a_statement",
    "ungrounded_label",
    "too_many_segments",
    "attribute_exists",
]


class SourceSpan(ApiModel):
    """A half-open range [start, end) of Unicode code points of the request's text."""

    start: int = Field(ge=0, le=3999)
    end: int = Field(ge=1, le=4000)


class SourceSegment(ApiModel):
    index: int = Field(ge=0, le=39)
    span: SourceSpan


class DraftNote(ApiModel):
    """Advisory notes on one draft for the reviewer; never submitted with the draft."""

    extractor: Literal["rules", "llm"]
    confidence: float = Field(ge=0, le=1)
    explanation: str | None = Field(default=None, max_length=300, exclude_if=lambda v: v is None)
    segment: int | None = Field(default=None, ge=0, le=39, exclude_if=lambda v: v is None)
    source_span: SourceSpan | None = Field(default=None, exclude_if=lambda v: v is None)


class UnresolvedPhrase(ApiModel):
    text: str = Field(min_length=1, max_length=400)
    reason: UnresolvedReason


class TeachResult(ApiModel):
    """`drafts` are in the contract's draft shape, ready for `POST /proposals/batch`;
    `draft_notes` has one entry per draft, in the same order. `parse_id` is set when the parse
    was recorded for usage learning; the client sends it back with the batch."""

    parse_id: uuid.UUID | None = None
    outcome: Literal["understood", "partly_understood", "not_understood"]
    domain_key: str | None
    intents: list[Intent] = Field(max_length=150)
    drafts: list[dict[str, Any]] = Field(max_length=150)
    statements: list[str]
    caption: str
    origin: Origin
    origin_detail: OriginDetail | None
    extractor: Extractor
    degraded: bool
    llm_outcome: LlmOutcome
    draft_notes: list[DraftNote] = Field(max_length=150)
    unresolved: list[UnresolvedPhrase] = Field(max_length=40)
    segments: list[SourceSegment] = Field(max_length=40)
