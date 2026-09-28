"""Audit entry DTO."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.api.actor import Actor
from app.models.api.base import ApiModel


class AuditEntry(ApiModel):
    id: int
    at: datetime
    actor: Actor
    kind: str
    what: str
    ok: bool
    proposal_id: uuid.UUID | None = None
    company_ids: list[uuid.UUID] = Field(default_factory=list)
    domain_key: str | None = None
