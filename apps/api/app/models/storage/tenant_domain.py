"""Storage mapping for the `tenant_domain` table: one tenant's domains, templates and custom."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

# `template_key`, and the domain key columns of audit entries, outbox rows and role scopes,
# reference `domain_template`; its mapping must be registered before the first flush, and no
# request path imports it otherwise.
from app.models.storage import domain_template as _template_mapping  # noqa: F401
from app.models.storage.base import Base


class TenantDomain(Base):
    __tablename__ = "tenant_domain"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    owner: Mapped[str] = mapped_column(server_default=text("''"))
    default_color: Mapped[str]
    template_key: Mapped[str | None] = mapped_column(ForeignKey("domain_template.key"))
    position: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
