"""Database access for the `domain_template` reference table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.domain_template import DomainTemplate


async def list_in_ring_order(session: AsyncSession) -> list[DomainTemplate]:
    result = await session.scalars(select(DomainTemplate).order_by(DomainTemplate.position))
    return list(result)
