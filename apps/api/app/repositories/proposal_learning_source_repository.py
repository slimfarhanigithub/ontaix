"""Database access for the `proposal_learning_source` table: the model output of a proposal."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.proposal_learning_source import ProposalLearningSource


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
    kind: str,
    draft_index: int,
    edited: bool = False,
    parse_id: uuid.UUID | None = None,
    expansion_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
) -> ProposalLearningSource:
    row = ProposalLearningSource(
        tenant_id=tenant_id,
        proposal_id=proposal_id,
        kind=kind,
        parse_id=parse_id,
        expansion_id=expansion_id,
        job_id=job_id,
        draft_index=draft_index,
        edited=edited,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> ProposalLearningSource | None:
    return await session.scalar(
        select(ProposalLearningSource).where(
            ProposalLearningSource.tenant_id == tenant_id,
            ProposalLearningSource.proposal_id == proposal_id,
        )
    )


async def list_same_source(
    session: AsyncSession, link: ProposalLearningSource
) -> list[ProposalLearningSource]:
    """Every link to the same parse, expansion or extraction job as `link`, itself included."""
    column = {
        "teach": ProposalLearningSource.parse_id,
        "expand": ProposalLearningSource.expansion_id,
        "extraction": ProposalLearningSource.job_id,
    }[link.kind]
    value = {"teach": link.parse_id, "expand": link.expansion_id, "extraction": link.job_id}[
        link.kind
    ]
    result = await session.scalars(
        select(ProposalLearningSource)
        .where(ProposalLearningSource.tenant_id == link.tenant_id, column == value)
        .order_by(ProposalLearningSource.draft_index)
    )
    return list(result)


async def list_for_proposals(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_ids: list[uuid.UUID]
) -> list[ProposalLearningSource]:
    if not proposal_ids:
        return []
    result = await session.scalars(
        select(ProposalLearningSource).where(
            ProposalLearningSource.tenant_id == tenant_id,
            ProposalLearningSource.proposal_id.in_(proposal_ids),
        )
    )
    return list(result)
