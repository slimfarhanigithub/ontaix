"""Storage mapping for the `sign_in_throttle` table: failure counters keyed by SHA-256."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, ThrottleKeyKind, pg_enum


class SignInThrottle(Base):
    __tablename__ = "sign_in_throttle"

    key_kind: Mapped[ThrottleKeyKind] = mapped_column(
        pg_enum(ThrottleKeyKind, "throttle_key_kind"), primary_key=True
    )
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
