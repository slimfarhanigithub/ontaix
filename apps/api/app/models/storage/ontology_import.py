"""Storage mapping for the `ontology_import` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import ActorKind, Base, pg_enum


class OntologyImport(Base):
    __tablename__ = "ontology_import"
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
            ["tenant_id", "parent_concept_id"],
            ["concept.tenant_id", "concept.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    actor_kind: Mapped[ActorKind] = mapped_column(pg_enum(ActorKind, "actor_kind"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    parent_concept_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    file_name: Mapped[str]
    format: Mapped[str]
    sha256: Mapped[bytes] = mapped_column(LargeBinary)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    individuals: Mapped[str] = mapped_column(server_default=text("'skip'"))
    draft_count: Mapped[int] = mapped_column(Integer)
    drafts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '24 hours'")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
