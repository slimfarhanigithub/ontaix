"""Database access for the `learning_example` table: the lessons learnt in one company.

Every read and write names the tenant and the company, so no query ever reaches another
company's lessons.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ProposalOrigin
from app.models.storage.learning_example import LearningExample

MAX_ACTIVE = 5000


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    signal: str,
    task: str,
    origin: ProposalOrigin,
    source_text: str,
    model_output: dict[str, Any] | None,
    final_structure: dict[str, Any] | None,
    proposal_ids: list[uuid.UUID],
    concept_ids: list[uuid.UUID],
    corrects_id: uuid.UUID | None,
    bulk: bool,
    actor_user_id: uuid.UUID,
) -> LearningExample:
    row = LearningExample(
        tenant_id=tenant_id,
        company_id=company_id,
        signal=signal,
        task=task,
        origin=origin,
        source_text=source_text,
        model_output=model_output,
        final_structure=final_structure,
        proposal_ids=proposal_ids,
        concept_ids=concept_ids,
        corrects_id=corrects_id,
        bulk=bulk,
        actor_user_id=actor_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, lesson_id: uuid.UUID
) -> LearningExample | None:
    return await session.scalar(
        select(LearningExample).where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.id == lesson_id,
        )
    )


async def list_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> list[LearningExample]:
    """Every lesson of the company, active and retired, newest first."""
    result = await session.scalars(
        select(LearningExample)
        .where(LearningExample.tenant_id == tenant_id, LearningExample.company_id == company_id)
        .order_by(LearningExample.created_at.desc(), LearningExample.id)
    )
    return list(result)


async def list_active(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, limit: int = MAX_ACTIVE
) -> list[LearningExample]:
    """The company's active lessons, newest first, at most `limit`."""
    result = await session.scalars(
        select(LearningExample)
        .where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.retired_at.is_(None),
        )
        .order_by(LearningExample.created_at.desc(), LearningExample.id)
        .limit(limit)
    )
    return list(result)


async def find_active_by_proposals(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    proposal_ids: list[uuid.UUID],
    signals: tuple[str, ...],
) -> LearningExample | None:
    """The newest active lesson of one of `signals` holding any of `proposal_ids`."""
    if not proposal_ids:
        return None
    return await session.scalar(
        select(LearningExample)
        .where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.retired_at.is_(None),
            LearningExample.signal.in_(signals),
            LearningExample.proposal_ids.overlap(proposal_ids),
        )
        .order_by(LearningExample.created_at.desc(), LearningExample.id)
        .limit(1)
    )


async def recent_by_actor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    signal: str,
    since: datetime,
    limit: int = 20,
) -> list[LearningExample]:
    """The active lessons of `signal` one user made in the company since `since`, newest
    first."""
    result = await session.scalars(
        select(LearningExample)
        .where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.actor_user_id == actor_user_id,
            LearningExample.signal == signal,
            LearningExample.retired_at.is_(None),
            LearningExample.created_at >= since,
        )
        .order_by(LearningExample.created_at.desc(), LearningExample.id)
        .limit(limit)
    )
    return list(result)


async def list_active_by_source(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    source_text: str,
    signal: str,
) -> list[LearningExample]:
    """The active lessons of `signal` whose source text equals `source_text` without case."""
    result = await session.scalars(
        select(LearningExample).where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.signal == signal,
            LearningExample.retired_at.is_(None),
            func.lower(LearningExample.source_text) == source_text.lower(),
        )
    )
    return list(result)


async def update_structure(
    session: AsyncSession,
    lesson: LearningExample,
    *,
    final_structure: dict[str, Any],
    proposal_ids: list[uuid.UUID],
    concept_ids: list[uuid.UUID],
    bulk: bool,
) -> None:
    lesson.final_structure = final_structure
    lesson.proposal_ids = proposal_ids
    lesson.concept_ids = concept_ids
    lesson.bulk = bulk
    await session.flush()


async def retire(session: AsyncSession, lesson: LearningExample, reason: str, at: datetime) -> None:
    lesson.retired_at = at
    lesson.retired_reason = reason
    await session.flush()


async def retire_by_concepts(
    session: AsyncSession, tenant_id: uuid.UUID, concept_ids: list[uuid.UUID], at: datetime
) -> list[LearningExample]:
    """Retire, as contradicted, every active lesson of the tenant naming one of `concept_ids`;
    returns the lessons retired."""
    if not concept_ids:
        return []
    result = await session.scalars(
        select(LearningExample).where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.retired_at.is_(None),
            LearningExample.concept_ids.overlap(concept_ids),
        )
    )
    rows = list(result)
    for row in rows:
        row.retired_at = at
        row.retired_reason = "contradicted"
    await session.flush()
    return rows


async def retire_over_cap(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, cap: int, at: datetime
) -> int:
    """Retire the oldest active lessons of the company beyond `cap`; returns how many."""
    excess = await session.scalars(
        select(LearningExample.id)
        .where(
            LearningExample.tenant_id == tenant_id,
            LearningExample.company_id == company_id,
            LearningExample.retired_at.is_(None),
        )
        .order_by(LearningExample.created_at.desc(), LearningExample.id)
        .offset(cap)
    )
    ids = list(excess)
    if not ids:
        return 0
    await session.execute(
        update(LearningExample)
        .where(LearningExample.id.in_(ids))
        .values(retired_at=at, retired_reason="cap")
        .execution_options(synchronize_session=False)
    )
    return len(ids)


async def delete(session: AsyncSession, lesson: LearningExample) -> None:
    await session.delete(lesson)
    await session.flush()


async def delete_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> int:
    result = await session.execute(
        delete_rows(LearningExample).where(
            LearningExample.tenant_id == tenant_id, LearningExample.company_id == company_id
        )
    )
    return result.rowcount or 0


async def delete_retired_before(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(
        delete_rows(LearningExample).where(LearningExample.retired_at < cutoff)
    )
    return result.rowcount or 0
