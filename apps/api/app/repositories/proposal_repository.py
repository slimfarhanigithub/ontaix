"""Database access for the `proposal` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import (
    ActorKind,
    ChangeKind,
    ProposalOrigin,
    ProposalState,
    ProposalType,
)
from app.models.storage.proposal import Proposal

OPEN_STATES = (ProposalState.PENDING, ProposalState.HALF_APPROVED)
DECISION_LOCK_NAMESPACE = "ontaix.proposal-decisions"
DECISION_LOCK_TIMEOUT_MS = 5000
LOCK_NOT_AVAILABLE = "55P03"


class DecisionLockTimeoutError(Exception):
    """The tenant's decision lock was not granted within `DECISION_LOCK_TIMEOUT_MS`."""


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


async def lock_open(session: AsyncSession, tenant_id: uuid.UUID) -> list[Proposal]:
    """The open proposals of the tenant, row-locked until the transaction ends.

    Rows are locked in one stable order and re-read from the database, so the states returned
    are the committed ones at the moment the lock was granted.
    """
    result = await session.scalars(
        select(Proposal)
        .where(Proposal.tenant_id == tenant_id, Proposal.state.in_(OPEN_STATES))
        .order_by(Proposal.created_at, Proposal.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(result)


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> Proposal | None:
    return await session.scalar(
        select(Proposal).where(Proposal.tenant_id == tenant_id, Proposal.id == proposal_id)
    )


async def get_for_update(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> Proposal | None:
    """One proposal, row-locked until the transaction ends and re-read after the lock."""
    return await session.scalar(
        select(Proposal)
        .where(Proposal.tenant_id == tenant_id, Proposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def lock_decisions(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Serialise every decision and proposal creation of one tenant until the transaction ends.

    A decision reads the whole open queue and may cascade to other proposals, and a new proposal
    may depend on a pending one, so none of them interleave: the second waits here until the
    first commits or rolls back. The wait, and every other lock wait of the transaction, is
    bounded by `DECISION_LOCK_TIMEOUT_MS`; past it `DecisionLockTimeoutError` is raised and the
    transaction must be rolled back.
    """
    await session.execute(
        select(func.set_config("lock_timeout", f"{DECISION_LOCK_TIMEOUT_MS}ms", True))
    )
    key = func.hashtextextended(f"{DECISION_LOCK_NAMESPACE}:{tenant_id}", 0)
    try:
        await session.execute(select(func.pg_advisory_xact_lock(key)))
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            raise DecisionLockTimeoutError(str(tenant_id)) from exc
        raise


async def mark_half_approved(session: AsyncSession, proposal: Proposal, why: str) -> None:
    proposal.state = ProposalState.HALF_APPROVED
    proposal.why = why
    await session.flush()


async def mark_decided(
    session: AsyncSession, proposal: Proposal, state: ProposalState, decided_at: datetime
) -> None:
    proposal.state = state
    proposal.decided_at = decided_at
    await session.flush()


async def detach_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> None:
    """Keep the history of a company's proposals when the company row is deleted."""
    result = await session.scalars(
        select(Proposal).where(Proposal.tenant_id == tenant_id, Proposal.company_id == company_id)
    )
    for proposal in result:
        proposal.company_id = None
    await session.flush()


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
    origin: ProposalOrigin,
    origin_detail: dict[str, Any] | None,
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
        origin=origin,
        origin_detail=origin_detail,
    )
    session.add(proposal)
    await session.flush()
    return proposal
