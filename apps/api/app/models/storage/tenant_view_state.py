"""Storage mapping for the `tenant_view_state` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class TenantViewState(Base):
    __tablename__ = "tenant_view_state"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    coverage: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
