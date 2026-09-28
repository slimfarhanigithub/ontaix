"""Storage mapping for the `group_role` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, RoleName, ScopeKind, pg_enum


class GroupRole(Base):
    __tablename__ = "group_role"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["user_group.tenant_id", "user_group.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "scope_company_id"],
            ["company.tenant_id", "company.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    role: Mapped[RoleName] = mapped_column(pg_enum(RoleName, "role_name"))
    scope_kind: Mapped[ScopeKind] = mapped_column(pg_enum(ScopeKind, "scope_kind"))
    scope_company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    scope_domain_key: Mapped[str | None] = mapped_column(ForeignKey("domain_template.key"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
