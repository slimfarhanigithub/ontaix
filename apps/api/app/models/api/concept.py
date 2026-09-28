"""Concept DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.attribute import Attribute
from app.models.api.base import ApiModel
from app.models.api.binding import Binding


class Concept(ApiModel):
    id: uuid.UUID
    company_id: uuid.UUID
    kind: Literal["root", "concept"]
    label: str
    sub: str
    domain_product_id: uuid.UUID | None = None
    domain_key: str | None = None
    color: str
    rule: str | None = None
    pending: bool
    conflict: bool
    parent_id: uuid.UUID | None = None
    birth_relation_id: uuid.UUID | None = None
    born_at: datetime
    x: float
    y: float
    pinned: bool
    dying_at: datetime | None = None
    bound: Binding | None = None
    attributes: list[Attribute] = Field(default_factory=list)
    relation_count: int
    state: Literal["awaiting approval", "approved", "certified"]
    is_specialisation: bool = False


class ConceptRename(ApiModel):
    label: str = Field(min_length=1, max_length=120)
