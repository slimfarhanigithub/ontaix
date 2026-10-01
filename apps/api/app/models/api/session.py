"""Sign-in, the current session and password change: the `/auth` shapes.

Password fields are write-only: they are read from requests and never appear in a response,
a log line or an audit entry.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.organization import OrganizationRef

MAX_PRESENTED_PASSWORD = 1024


class SignInRequest(ApiModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PRESENTED_PASSWORD, repr=False)


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=MAX_PRESENTED_PASSWORD, repr=False)
    new_password: str = Field(min_length=1, max_length=MAX_PRESENTED_PASSWORD, repr=False)


class SessionAccount(ApiModel):
    id: uuid.UUID
    email: str
    name: str


class SupportInfo(ApiModel):
    organization: OrganizationRef
    until: datetime
    reason: str


class Session(ApiModel):
    kind: Literal["member", "platform"]
    account: SessionAccount
    organization: OrganizationRef | None = None
    user_id: uuid.UUID | None = None
    platform_roles: list[Literal["super_admin"]] | None = None
    support: SupportInfo | None = None
    csrf_token: str
    must_change_password: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime
