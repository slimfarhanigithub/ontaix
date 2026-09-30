"""Storage mapping for the `company` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class Company(Base):
    __tablename__ = "company"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    key: Mapped[str]
    name: Mapped[str]
    sub: Mapped[str] = mapped_column(server_default=text("''"))
    position: Mapped[int] = mapped_column(Integer)
    is_home: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    learning: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    dying_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
