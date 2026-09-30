"""Storage mapping for the `learning_example` table: one lesson learnt from a human decision."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, ProposalOrigin, pg_enum


class LearningExample(Base):
    __tablename__ = "learning_example"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
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
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    signal: Mapped[str]
    task: Mapped[str]
    origin: Mapped[ProposalOrigin] = mapped_column(pg_enum(ProposalOrigin, "proposal_origin"))
    source_text: Mapped[str]
    model_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    final_structure: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    proposal_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default=text("'{}'"))
    concept_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default=text("'{}'"))
    # The (tenant, corrects_id) foreign key sets only corrects_id to null; it is left to the
    # database and not declared here, so the ORM never tries to null tenant_id.
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    bulk: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_reason: Mapped[str | None]
