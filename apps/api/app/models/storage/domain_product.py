"""Storage mapping for the `domain_product` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class DomainProduct(Base):
    __tablename__ = "domain_product"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    template_key: Mapped[str] = mapped_column(ForeignKey("domain_template.key"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    hidden: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
