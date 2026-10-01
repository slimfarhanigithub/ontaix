"""Storage mapping for the `account` table: a sign-in identity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class Account(Base):
    __tablename__ = "account"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str]
    name: Mapped[str]
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_platform: Mapped[bool] = mapped_column(Boolean, Computed("tenant_id IS NULL"))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
