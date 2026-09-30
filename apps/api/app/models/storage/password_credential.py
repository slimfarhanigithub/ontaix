"""Storage mapping for the `password_credential` table: an argon2id hash, never a password."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, PasswordSetReason, pg_enum


class PasswordCredential(Base):
    __tablename__ = "password_credential"

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    hash: Mapped[str]
    must_change: Mapped[bool] = mapped_column(Boolean)
    set_reason: Mapped[PasswordSetReason] = mapped_column(
        pg_enum(PasswordSetReason, "password_set_reason")
    )
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    set_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    def __repr__(self) -> str:
        return f"PasswordCredential(account_id={self.account_id!r})"
