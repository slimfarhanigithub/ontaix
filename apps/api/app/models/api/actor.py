"""Who did something: a user, an agent or the system."""

from __future__ import annotations

import uuid
from typing import Literal

from app.models.api.base import ApiModel


class Actor(ApiModel):
    kind: Literal["user", "agent", "system"]
    id: uuid.UUID | None = None
    name: str | None = None
