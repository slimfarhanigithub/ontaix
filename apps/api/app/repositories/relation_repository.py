"""Database access for the `relation` table."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
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


async def touching(session: AsyncSession, concept_id: uuid.UUID) -> list[Relation]:
    result = await session.scalars(
        select(Relation).where(or_(Relation.a_id == concept_id, Relation.b_id == concept_id))
    )
    return list(result)


async def find_triple(
    session: AsyncSession, a_id: uuid.UUID, label: str, b_id: uuid.UUID
) -> Relation | None:
    return await session.scalar(
        select(Relation).where(
            Relation.a_id == a_id,
            Relation.b_id == b_id,
            func.lower(Relation.label) == label.lower(),
            Relation.dying_at.is_(None),
        )
    )


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
