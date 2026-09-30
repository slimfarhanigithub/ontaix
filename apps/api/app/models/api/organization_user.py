"""An organization's accounts as the platform portal reads and writes them.

Password fields are write-only: never returned, logged or audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.session import MAX_PRESENTED_PASSWORD

MAX_GROUPS = 50


class GroupRef(ApiModel):
    id: uuid.UUID
    name: str


class OrganizationUser(ApiModel):
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    name: str
    department: str | None = None
    status: Literal["active", "disabled"]
    must_change_password: bool
    locked: bool
    groups: list[GroupRef]
    created_at: datetime
    last_sign_in_at: datetime | None = None


class OrganizationUserCreate(ApiModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=1, max_length=MAX_PRESENTED_PASSWORD, repr=False)
    group_ids: list[uuid.UUID] = Field(max_length=MAX_GROUPS)


class OrganizationUserUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    group_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_GROUPS)


class PasswordReset(ApiModel):
    new_password: str = Field(min_length=1, max_length=MAX_PRESENTED_PASSWORD, repr=False)


class SupportSessionStart(ApiModel):
    reason: str = Field(min_length=3, max_length=300)
