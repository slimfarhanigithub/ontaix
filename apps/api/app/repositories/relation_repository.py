"""Database access for the `relation` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RelationKind
from app.models.storage.relation import Relation


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Relation]:
    result = await session.scalars(
        select(Relation).where(Relation.tenant_id == tenant_id).order_by(Relation.created_at)
    )
    return list(result)


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, relation_id: uuid.UUID
) -> Relation | None:
    return await session.scalar(
        select(Relation).where(Relation.tenant_id == tenant_id, Relation.id == relation_id)
    )


async def exists(session: AsyncSession, tenant_id: uuid.UUID, relation_id: uuid.UUID) -> bool:
    """True when the committed row is still there and not dying, whatever the session caches."""
    found = await session.scalar(
        select(Relation.id).where(
            Relation.tenant_id == tenant_id,
            Relation.id == relation_id,
            Relation.dying_at.is_(None),
        )
    )
    return found is not None


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    kind: RelationKind,
    label: str,
    rest: int,
    seed: float,
    pending: bool,
) -> Relation:
    relation = Relation(
        tenant_id=tenant_id,
        a_id=a_id,
        b_id=b_id,
        kind=kind,
        label=label,
        rest=rest,
        seed=seed,
        pending=pending,
    )
    session.add(relation)
    await session.flush()
    return relation


async def delete(session: AsyncSession, relation: Relation) -> None:
    await session.delete(relation)
    await session.flush()


async def clear_pending(session: AsyncSession, relation: Relation) -> None:
    relation.pending = False
    await session.flush()


async def update(
    session: AsyncSession, relation: Relation, *, label: str, a_id: uuid.UUID, b_id: uuid.UUID
) -> None:
    relation.label = label
    relation.a_id = a_id
    relation.b_id = b_id
    await session.flush()


async def mark_dying(session: AsyncSession, relation: Relation, at: datetime) -> None:
    """Stamp the moment the relation starts dying; it is deleted later in the same transaction."""
    relation.dying_at = at
    await session.flush()
