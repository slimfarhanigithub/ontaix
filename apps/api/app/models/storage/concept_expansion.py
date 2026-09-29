"""Storage mapping for the `concept_expansion` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class ConceptExpansion(Base):
    __tablename__ = "concept_expansion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_user_id"],
            ["app_user.tenant_id", "app_user.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "concept_id"], ["concept.tenant_id", "concept.id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    concept_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    depth: Mapped[int | None] = mapped_column(Integer)
    max_children: Mapped[int | None] = mapped_column(Integer)
    draft_count: Mapped[int] = mapped_column(Integer)
    drafts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '1 hour'")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
