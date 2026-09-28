"""Storage mapping for the `concept` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, NodeKind, pg_enum


class Concept(Base):
    __tablename__ = "concept"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "domain_product_id"],
            ["domain_product.tenant_id", "domain_product.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["concept.tenant_id", "concept.id"], ondelete="SET NULL"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[NodeKind] = mapped_column(
        pg_enum(NodeKind, "node_kind"), server_default=text("'concept'")
    )
    label: Mapped[str]
    sub: Mapped[str] = mapped_column(server_default=text("''"))
    domain_product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rule: Mapped[str | None]
    pending: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    conflict: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    birth_relation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    birth_action: Mapped[str | None]
    birth_reverse: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    born_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    x: Mapped[float] = mapped_column(Float, server_default=text("0"))
    y: Mapped[float] = mapped_column(Float, server_default=text("0"))
    pinned: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    dying_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
