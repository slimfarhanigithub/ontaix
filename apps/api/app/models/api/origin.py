"""Provenance DTOs: how the content of a proposal entered Ontaix, and the import it cites."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel

Origin = Literal["text", "speech", "document", "ontology_import"]
InputOrigin = Literal["text", "speech"]
ImportMediaType = Literal[
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/html",
]


class ImportRef(ApiModel):
    """One stored sentence of a document import, cited by a teach parse or a draft."""

    import_id: uuid.UUID
    sentence_index: int = Field(ge=0, le=1999)


class DocumentPosition(ApiModel):
    """A 1-based page, paragraph, slide or sheet; `row` only with `sheet`."""

    unit: Literal["page", "paragraph", "slide", "sheet"]
    index: int = Field(ge=1, le=100000)
    row: int | None = Field(default=None, ge=1, le=1048576, exclude_if=lambda v: v is None)


class ImportOriginDetail(ApiModel):
    file_name: str = Field(min_length=1, max_length=255)
    media_type: ImportMediaType


class OriginDetail(ApiModel):
    """Where a `document` proposal came from, copied from the stored import."""

    file_name: str = Field(min_length=1, max_length=255)
    media_type: ImportMediaType
    sentence_index: int = Field(ge=0, le=1999)
    position: DocumentPosition | None = Field(default=None, exclude_if=lambda v: v is None)
