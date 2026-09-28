"""Storage mapping for the `attribute` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, SmallInteger, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import AttributeState, AttributeType, Base, pg_enum


class Attribute(Base):
    __tablename__ = "attribute"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "concept_id"], ["concept.tenant_id", "concept.id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    concept_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str]
    type: Mapped[AttributeType] = mapped_column(pg_enum(AttributeType, "attribute_type"))
    col: Mapped[str]
    fill: Mapped[int] = mapped_column(SmallInteger)
    state: Mapped[AttributeState] = mapped_column(
        pg_enum(AttributeState, "attribute_state"), server_default=text("'proposed'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
