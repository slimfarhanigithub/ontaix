"""Relation DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.api.base import ApiModel


class Relation(ApiModel):
    id: uuid.UUID
    a_id: uuid.UUID
    b_id: uuid.UUID
    a_label: str
    b_label: str
    kind: Literal["rel", "isa", "same", "clash"]
    label: str
    rest: float
    seed: float
    pending: bool
    dying_at: datetime | None = None
    company_ids: list[uuid.UUID]
    scope: str
    state: Literal["awaiting approval", "approved"]


class RelationEdit(ApiModel):
    action: str | None = Field(default=None, min_length=1, max_length=60)
    reverse: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> RelationEdit:
        if self.action is None and self.reverse is None:
            raise ValueError("at least one of action or reverse is required")
        return self


class EquivalenceDraft(ApiModel):
    a_id: uuid.UUID
    b_id: uuid.UUID
    caption: str | None = Field(default=None, max_length=300)
