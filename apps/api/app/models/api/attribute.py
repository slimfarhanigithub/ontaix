"""Attribute DTO."""

from __future__ import annotations

import uuid
from typing import Literal

from app.models.api.base import ApiModel


class Attribute(ApiModel):
    id: uuid.UUID
    concept_id: uuid.UUID
    source_id: uuid.UUID | None = None
    name: str
    type: Literal["id", "text", "number", "ref", "date"]
    col: str
    fill: int
    state: Literal["proposed", "approved"]
