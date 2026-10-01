"""A group with its role assignments, as the platform portal's group picker reads it."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.models.api.base import ApiModel


class Scope(ApiModel):
    kind: Literal["tenant", "company", "domain"]
    company_id: uuid.UUID | None = None
    domain_key: str | None = None
    label: str


class RoleAssignment(ApiModel):
    id: uuid.UUID
    group_id: uuid.UUID
    role: Literal["owner", "builder", "governor", "member", "administrator", "auditor", "agent"]
    scope: Scope


class Group(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    valid_until: datetime | None = None
    member_count: int
    roles: list[RoleAssignment]
