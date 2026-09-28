"""Database access for the `concept` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import NodeKind
from app.models.storage.concept import Concept


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Concept]:
    result = await session.scalars(
        select(Concept).where(Concept.tenant_id == tenant_id).order_by(Concept.created_at)
    )
    return list(result)


async def get(session: AsyncSession, tenant_id: uuid.UUID, concept_id: uuid.UUID) -> Concept | None:
    return await session.scalar(
        select(Concept).where(Concept.tenant_id == tenant_id, Concept.id == concept_id)
    )


async def exists(session: AsyncSession, tenant_id: uuid.UUID, concept_id: uuid.UUID) -> bool:
    """True when the committed row is still there and not dying, whatever the session caches."""
    found = await session.scalar(
        select(Concept.id).where(
            Concept.tenant_id == tenant_id,
            Concept.id == concept_id,
            Concept.dying_at.is_(None),
        )
    )
    return found is not None


async def label_taken(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, label: str
) -> bool:
    """True when a live cell of the company already carries the label, ignoring case."""
    found = await session.scalar(
        select(Concept.id).where(
            Concept.tenant_id == tenant_id,
            Concept.company_id == company_id,
            func.lower(Concept.label) == label.lower(),
            Concept.dying_at.is_(None),
        )
    )
    return found is not None


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    kind: NodeKind,
    label: str,
    sub: str,
    domain_product_id: uuid.UUID | None,
    rule: str | None,
    pending: bool,
    parent_id: uuid.UUID | None,
    birth_action: str | None,
    birth_reverse: bool,
    born_at: datetime,
    x: float,
    y: float,
) -> Concept:
    concept = Concept(
        tenant_id=tenant_id,
        company_id=company_id,
        kind=kind,
        label=label,
        sub=sub,
        domain_product_id=domain_product_id,
        rule=rule,
        pending=pending,
        parent_id=parent_id,
        birth_action=birth_action,
        birth_reverse=birth_reverse,
        born_at=born_at,
        x=x,
        y=y,
    )
    session.add(concept)
    await session.flush()
    return concept


async def delete(session: AsyncSession, concept: Concept) -> None:
    await session.delete(concept)
    await session.flush()


async def set_birth_relation(
    session: AsyncSession, concept: Concept, relation_id: uuid.UUID
) -> None:
    concept.birth_relation_id = relation_id
    await session.flush()


async def clear_pending(session: AsyncSession, concept: Concept) -> None:
    concept.pending = False
    await session.flush()


async def rename(session: AsyncSession, concept: Concept, label: str) -> None:
    concept.label = label
    await session.flush()


async def mark_dying(session: AsyncSession, concept: Concept, at: datetime) -> None:
    """Stamp the moment the cell starts dying; the row is deleted later in the same transaction."""
    concept.dying_at = at
    await session.flush()
