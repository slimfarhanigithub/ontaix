"""Ontology import DTOs: the mapped tree, its notes and skipped items, and the submission."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.ontology_import.parsed_ontology import OntologyFormat, SkipReason


class OntologyImportNote(ApiModel):
    source: str = Field(max_length=400)
    label_language: str | None = Field(default=None, max_length=35)
    depth: int | None = Field(default=None, ge=1)
    requires: list[int] = Field(default_factory=list, max_length=2)


class SkippedItem(ApiModel):
    source: str = Field(max_length=400)
    label: str | None = Field(default=None, max_length=120, exclude_if=lambda v: v is None)
    reason: SkipReason


class OntologyImportResult(ApiModel):
    ontology_import_id: uuid.UUID
    expires_at: datetime
    company_id: uuid.UUID
    parent_concept_id: uuid.UUID | None
    format: OntologyFormat
    languages: list[str] = Field(max_length=10)
    individuals: Literal["skip", "as_concepts"]
    # Each draft in the wire shape of `ProposalDraft`, as the server mapped and stored it.
    drafts: list[dict[str, Any]] = Field(max_length=20000)
    notes: list[OntologyImportNote] = Field(max_length=20000)
    skipped: list[SkippedItem] = Field(max_length=100000)


class OntologyImportSubmission(ApiModel):
    indexes: list[int] = Field(min_length=1, max_length=20000)
