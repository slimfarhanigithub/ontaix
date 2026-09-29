"""Storage mapping for the `document_extraction_job` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class DocumentExtractionJob(Base):
    __tablename__ = "document_extraction_job"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_user_id"],
            ["app_user.tenant_id", "app_user.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(server_default=text("'queued'"))
    phase: Mapped[str | None]
    chunks: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    outline_chunks_done: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    section_chunks_done: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    token_ceiling: Mapped[int] = mapped_column(Integer)
    node_ceiling: Mapped[int] = mapped_column(Integer)
    tokens_used: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    outline: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    drafts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    notes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    unresolved: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    draft_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    degraded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    failure_reason: Mapped[str | None]
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_epoch: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
