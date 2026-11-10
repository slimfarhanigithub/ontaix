"""Storage mapping for the `account` table: a sign-in identity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class Account(Base):
    __tablename__ = "account"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str]
    name: Mapped[str]
    is_platform: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # The portal language the person chose (`en`, `fr`, `de`); None follows the browser.
    language: Mapped[str | None]
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
