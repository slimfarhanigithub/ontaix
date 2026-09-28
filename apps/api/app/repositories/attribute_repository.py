"""Database access for the `attribute` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.attribute import Attribute


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Attribute]:
    result = await session.scalars(
        select(Attribute).where(Attribute.tenant_id == tenant_id).order_by(Attribute.created_at)
    )
    return list(result)
