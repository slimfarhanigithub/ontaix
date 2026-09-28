"""Database access for the `proposal` table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ActorKind, ChangeKind, ProposalState, ProposalType
from app.models.storage.proposal import Proposal

OPEN_STATES = (ProposalState.PENDING, ProposalState.HALF_APPROVED)


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Proposal]:
    result = await session.scalars(
        select(Proposal).where(Proposal.tenant_id == tenant_id).order_by(Proposal.created_at)
    )
    return list(result)


async def list_open(session: AsyncSession, tenant_id: uuid.UUID) -> list[Proposal]:
    result = await session.scalars(
        select(Proposal)
        .where(Proposal.tenant_id == tenant_id, Proposal.state.in_(OPEN_STATES))
        .order_by(Proposal.created_at)
    )
    return list(result)


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> Proposal | None:
    return await session.scalar(
        select(Proposal).where(Proposal.tenant_id == tenant_id, Proposal.id == proposal_id)
    )


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    type: ProposalType,
    change_kind: ChangeKind | None,
    title: str,
    color: str,
    company_id: uuid.UUID | None,
    domain_product_id: uuid.UUID | None,
    parent_label: str | None,
    deps: list[str],
    wait_for: str | None,
    html: str,
    why: str | None,
    caption: str | None,
    payload: dict[str, Any],
    concept_id: uuid.UUID | None,
    relation_id: uuid.UUID | None,
    relation_ids: list[uuid.UUID],
    proposer_kind: ActorKind,
    proposer_user_id: uuid.UUID | None,
    bulk: bool,
) -> Proposal:
    proposal = Proposal(
        tenant_id=tenant_id,
        type=type,
        change_kind=change_kind,
        title=title,
        color=color,
        company_id=company_id,
        domain_product_id=domain_product_id,
        parent_label=parent_label,
        deps=deps,
        wait_for=wait_for,
        html=html,
        why=why,
        caption=caption,
        payload=payload,
        concept_id=concept_id,
        relation_id=relation_id,
        relation_ids=relation_ids,
        proposer_kind=proposer_kind,
        proposer_user_id=proposer_user_id,
        bulk=bulk,
    )
    session.add(proposal)
    await session.flush()
    return proposal
