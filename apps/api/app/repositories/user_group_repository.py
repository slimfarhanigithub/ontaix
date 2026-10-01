"""Database access for the `user_group` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.user_group import UserGroup


async def create(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, description: str
) -> UserGroup:
    group = UserGroup(tenant_id=tenant_id, name=name, description=description)
    session.add(group)
    await session.flush()
    return group


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[UserGroup]:
    """The organization's groups, by name."""
    result = await session.scalars(
        select(UserGroup).where(UserGroup.tenant_id == tenant_id).order_by(UserGroup.name)
    )
    return list(result)
