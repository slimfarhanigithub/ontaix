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
    text: str | None = Field(default=None, min_length=1, max_length=400)
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None

    @model_validator(mode="after")
    def _one_source(self) -> TeachRequest:
        if (self.text is None) == (self.import_ref is None):
            raise ValueError("exactly one of text or importRef is required")
        return self


class Intent(ApiModel):
    kind: Literal["spec", "rel"]
    subject: str
    predicate: str | None = Field(default=None, exclude_if=lambda v: v is None)
    object: str
    rule: str | None = Field(default=None, exclude_if=lambda v: v is None)
    subject_resolved: uuid.UUID | None
    object_resolved: uuid.UUID | None


class TeachResult(ApiModel):
    """`drafts` are in the contract's draft shape, ready for `POST /proposals/batch`."""

    outcome: Literal["understood", "partly_understood", "not_understood"]
    domain_key: str | None
    intents: list[Intent]
    drafts: list[dict[str, Any]]
    statements: list[str]
    caption: str
    origin: Origin
    origin_detail: OriginDetail | None
