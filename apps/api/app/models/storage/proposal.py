"""Storage mapping for the `proposal` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import (
    ActorKind,
    Base,
    ChangeKind,
    ProposalState,
    ProposalType,
    pg_enum,
)


class Proposal(Base):
    __tablename__ = "proposal"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["company.tenant_id", "company.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "domain_product_id"],
            ["domain_product.tenant_id", "domain_product.id"],
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "concept_id"], ["concept.tenant_id", "concept.id"], ondelete="SET NULL"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "relation_id"], ["relation.tenant_id", "relation.id"], ondelete="SET NULL"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "proposer_user_id"],
            ["app_user.tenant_id", "app_user.id"],
            ondelete="SET NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"))
    type: Mapped[ProposalType] = mapped_column(pg_enum(ProposalType, "proposal_type"))
    change_kind: Mapped[ChangeKind | None] = mapped_column(pg_enum(ChangeKind, "change_kind"))
    state: Mapped[ProposalState] = mapped_column(
        pg_enum(ProposalState, "proposal_state"), server_default=text("'pending'")
    )
    title: Mapped[str]
    color: Mapped[str]
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    domain_product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    parent_label: Mapped[str | None]
    deps: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    wait_for: Mapped[str | None]
    html: Mapped[str]
    why: Mapped[str | None]
    caption: Mapped[str | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    concept_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    relation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    relation_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default=text("'{}'"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    binding_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default=text("'{}'"))
    attribute_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposer_kind: Mapped[ActorKind] = mapped_column(pg_enum(ActorKind, "actor_kind"))
    proposer_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposer_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    bulk: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
