"""Database access for the `proposal_approval` table."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.proposal_approval import ProposalApproval


async def list_for_proposals(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_ids: Iterable[uuid.UUID]
) -> list[ProposalApproval]:
    ids = list(proposal_ids)
    if not ids:
        return []
    result = await session.scalars(
        select(ProposalApproval)
        .where(ProposalApproval.tenant_id == tenant_id, ProposalApproval.proposal_id.in_(ids))
        .order_by(ProposalApproval.ordinal)
    )
    return list(result)


async def create(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
    ordinal: int,
    user_id: uuid.UUID,
) -> ProposalApproval:
    approval = ProposalApproval(
        tenant_id=tenant_id, proposal_id=proposal_id, ordinal=ordinal, user_id=user_id
    )
    session.add(approval)
    await session.flush()
    return approval
