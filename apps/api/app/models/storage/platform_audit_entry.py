"""Storage mapping for the append-only `platform_audit_entry` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Uuid, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class PlatformAuditEntry(Base):
    __tablename__ = "platform_audit_entry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str]
    ok: Mapped[bool] = mapped_column(Boolean)
    target_tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    target_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    what: Mapped[str]
    client_ip: Mapped[str | None] = mapped_column(INET)
