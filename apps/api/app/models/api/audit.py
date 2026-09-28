"""Audit entry DTO."""

from __future__ import annotations

import uuid
from datetime import datetime

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
