"""Storage mapping for the `group_member` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class GroupMember(Base):
    __tablename__ = "group_member"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["user_group.tenant_id", "user_group.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["app_user.tenant_id", "app_user.id"], ondelete="CASCADE"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
