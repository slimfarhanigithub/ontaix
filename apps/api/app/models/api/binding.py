"""Binding DTO: the bind link from a source to a concept."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel


class Binding(ApiModel):
    id: uuid.UUID
    kind: Literal["bind"] = "bind"
    source_id: uuid.UUID
    source_label: str
    concept_id: uuid.UUID
    records: int
    fresh: str
    seed: float | None = Field(default=None, ge=0, lt=1)
    pending: bool
