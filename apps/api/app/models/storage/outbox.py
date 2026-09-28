"""Storage mapping for the `outbox` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import ActorKind, Base, pg_enum


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="SET NULL"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, server_default=text("gen_random_uuid()"))
    aggregate: Mapped[str]
    action: Mapped[str]
    subject: Mapped[str]
    visibility: Mapped[str]
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_kind: Mapped[ActorKind] = mapped_column(pg_enum(ActorKind, "actor_kind"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    bulk: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
