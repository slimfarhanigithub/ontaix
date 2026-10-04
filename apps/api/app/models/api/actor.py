"""Who did something: a user, an agent, the system, or a super admin (`platform`).

`platform_account_id` on a `user` actor marks platform access: the user is the super admin
acting inside the organization after entering it, and the id is his platform account.
"""

from __future__ import annotations

import uuid
from typing import Literal

from app.models.api.base import ApiModel


class Actor(ApiModel):
    kind: Literal["user", "agent", "system", "platform"]
    id: uuid.UUID | None = None
    name: str | None = None
    platform_account_id: uuid.UUID | None = None
