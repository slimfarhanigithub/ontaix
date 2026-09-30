"""Storage mapping for the `organization_settings` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, CompanyMode, pg_enum


class OrganizationSettings(Base):
    __tablename__ = "organization_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    company_mode: Mapped[CompanyMode] = mapped_column(
        pg_enum(CompanyMode, "company_mode"), server_default=text("'multiple'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
