"""Response of `POST /import/sentences`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.origin import DocumentPosition, ImportOriginDetail


class ImportResult(ApiModel):
    import_id: uuid.UUID
    expires_at: datetime
    file_name: str
    sentences: list[str] = Field(max_length=2000)
    # Pieces of extracted text left out of `sentences`, such as those under 13 characters.
    skipped: int = Field(ge=0)
    origin: Literal["document"]
    origin_detail: ImportOriginDetail
    positions: list[DocumentPosition | None] = Field(max_length=2000)
