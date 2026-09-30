"""Storage mapping for the append-only `audit_entry` table.

Actor and proposal ids are plain columns without foreign keys, so a deletion elsewhere never
turns into an update of the log.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import ActorKind, Base, ProposalOrigin, pg_enum


class AuditEntry(Base):
    __tablename__ = "audit_entry"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "domain_key"],
            ["tenant_domain.tenant_id", "tenant_domain.key"],
            ondelete="SET NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="RESTRICT"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    actor_kind: Mapped[ActorKind] = mapped_column(pg_enum(ActorKind, "actor_kind"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str]
    what: Mapped[str]
    ok: Mapped[bool] = mapped_column(Boolean)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    origin: Mapped[ProposalOrigin | None] = mapped_column(
        pg_enum(ProposalOrigin, "proposal_origin")
    )
    company_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default=text("'{}'"))
    # The tenant domain key of the proposal's domain product, when it has one.
    domain_key: Mapped[str | None]
