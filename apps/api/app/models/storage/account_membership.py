"""Storage mapping for the `account_membership` table: an account's membership of one
organization, through that organization's directory user."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class AccountMembership(Base):
    __tablename__ = "account_membership"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["app_user.tenant_id", "app_user.id"], ondelete="CASCADE"
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    is_platform: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    @property
    def active(self) -> bool:
        """Neither disabled nor removed; whether the organization is enabled is the caller's."""
        return self.disabled_at is None and self.removed_at is None
