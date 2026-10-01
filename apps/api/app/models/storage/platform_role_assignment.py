"""Storage mapping for the `platform_role_assignment` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, PlatformRoleName, pg_enum


class PlatformRoleAssignment(Base):
    __tablename__ = "platform_role_assignment"

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    role: Mapped[PlatformRoleName] = mapped_column(
        pg_enum(PlatformRoleName, "platform_role_name"), primary_key=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
