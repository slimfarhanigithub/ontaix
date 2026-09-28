"""Storage mapping for the `proposal_approval` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, SmallInteger, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class ProposalApproval(Base):
    __tablename__ = "proposal_approval"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"], ["proposal.tenant_id", "proposal.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["app_user.tenant_id", "app_user.id"], ondelete="RESTRICT"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(SmallInteger)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
