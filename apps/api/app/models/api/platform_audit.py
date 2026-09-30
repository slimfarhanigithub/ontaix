"""An entry of the platform audit log, read by super admins at `GET /admin/audit`."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.api.base import ApiModel
from app.models.api.organization import OrganizationRef


class PlatformActor(ApiModel):
    account_id: uuid.UUID
    email: str


class PlatformAuditEntry(ApiModel):
    id: int
    at: datetime
    actor: PlatformActor | None = None
    action: str
    ok: bool
    organization: OrganizationRef | None = None
    target_account_id: uuid.UUID | None = None
    what: str
    client_ip: str | None = None
