"""Storage mapping for the `document_import` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, LargeBinary, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import ActorKind, Base, pg_enum


class DocumentImport(Base):
    __tablename__ = "document_import"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_user_id"],
            ["app_user.tenant_id", "app_user.id"],
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
    file_name: Mapped[str]
    media_type: Mapped[str]
    sha256: Mapped[bytes] = mapped_column(LargeBinary)
    sentence_count: Mapped[int] = mapped_column(Integer)
    extracted_chars: Mapped[int] = mapped_column(Integer)
    ocr_pages: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '1 hour'")
    )
