"""Database access for the `group_member` table."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.group_member import GroupMember


async def add(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID, user_id: uuid.UUID
) -> GroupMember:
    member = GroupMember(tenant_id=tenant_id, group_id=group_id, user_id=user_id)
    session.add(member)
    await session.flush()
    return member


async def remove(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    await session.execute(
        delete(GroupMember)
        .where(
            GroupMember.tenant_id == tenant_id,
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
        .execution_options(synchronize_session=False)
    )


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[GroupMember]:
    result = await session.scalars(select(GroupMember).where(GroupMember.tenant_id == tenant_id))
    return list(result)
