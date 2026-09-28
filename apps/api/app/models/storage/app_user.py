"""Storage mapping for the `app_user` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="SET NULL"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    issuer: Mapped[str]
    subject: Mapped[str]
    email: Mapped[str]
    name: Mapped[str]
    department: Mapped[str | None]
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
