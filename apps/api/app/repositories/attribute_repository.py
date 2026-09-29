"""Database access for the `attribute` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.attribute import Attribute
from app.models.storage.base import AttributeState, AttributeType


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Attribute]:
    result = await session.scalars(
        select(Attribute).where(Attribute.tenant_id == tenant_id).order_by(Attribute.created_at)
    )
    return list(result)


async def name_taken(
    session: AsyncSession, tenant_id: uuid.UUID, concept_id: uuid.UUID, name: str
) -> bool:
    """True when the concept already has an attribute of that name in the committed data."""
    found = await session.scalar(
        select(Attribute.id).where(
            Attribute.tenant_id == tenant_id,
            Attribute.concept_id == concept_id,
            Attribute.name == name,
        )
    )
    return found is not None


async def create_taught(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    concept_id: uuid.UUID,
    name: str,
    type: AttributeType,
    value: str,
) -> Attribute:
    """A proposed taught attribute: a stated value, with no source, column or fill."""
    attribute = Attribute(
        tenant_id=tenant_id,
        concept_id=concept_id,
        source_id=None,
        name=name,
        type=type,
        col=None,
        fill=None,
        value=value,
        state=AttributeState.PROPOSED,
    )
    session.add(attribute)
    await session.flush()
    return attribute


async def approve(session: AsyncSession, attribute: Attribute) -> None:
    attribute.state = AttributeState.APPROVED
    await session.flush()


async def delete(session: AsyncSession, attribute: Attribute) -> None:
    await session.delete(attribute)
    await session.flush()
