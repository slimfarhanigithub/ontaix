"""Storage mapping for the `relation` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, RelationKind, pg_enum


class Relation(Base):
    __tablename__ = "relation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "a_id"], ["concept.tenant_id", "concept.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "b_id"], ["concept.tenant_id", "concept.id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    a_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    b_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[RelationKind] = mapped_column(pg_enum(RelationKind, "relation_kind"))
    label: Mapped[str]
    rest: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    seed: Mapped[float] = mapped_column(Float)
    pending: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    dying_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
