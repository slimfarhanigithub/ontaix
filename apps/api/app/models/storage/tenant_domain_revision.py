"""Storage mapping for the `tenant_domain_revision` table: a domain's name, colour and owner."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class TenantDomainRevision(Base):
    __tablename__ = "tenant_domain_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "key"],
            ["tenant_domain.tenant_id", "tenant_domain.key"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]
    color: Mapped[str]
    owner: Mapped[str]
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
