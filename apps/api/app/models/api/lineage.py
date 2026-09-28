"""Lineage drawer DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.concept import Concept


class LineageStep(ApiModel):
    concept_id: uuid.UUID
    label: str
    how: str
    domain_name: str | None = None
    pending: bool
    born_at: datetime


class LineageNode(ApiModel):
    concept_id: uuid.UUID
    label: str
    how: str
    pending: bool
    below: int
    children: list[LineageNode] = Field(default_factory=list)


class DataLineage(ApiModel):
    source_id: uuid.UUID
    source_label: str
    concept_id: uuid.UUID
    concept_label: str
    records: int
    fresh: str
    attributes: int


class Lineage(ApiModel):
    concept: Concept
    ancestors: list[LineageStep]
    descendants: list[LineageNode]
    data_lineage: list[DataLineage]
    set_ids: list[uuid.UUID]
    caption: str
