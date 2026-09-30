"""Storage mapping for the `proposal_learning_source` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class ProposalLearningSource(Base):
    __tablename__ = "proposal_learning_source"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"], ["proposal.tenant_id", "proposal.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parse_id"], ["teach_parse.tenant_id", "teach_parse.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "expansion_id"],
            ["concept_expansion.tenant_id", "concept_expansion.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["document_extraction_job.tenant_id", "document_extraction_job.id"],
            ondelete="CASCADE",
        ),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    kind: Mapped[str]
    parse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    expansion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    draft_index: Mapped[int] = mapped_column(Integer)
    edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
