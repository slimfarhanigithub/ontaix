"""Database access for the `group_role` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.group_member import GroupMember
from app.models.storage.group_role import GroupRole
from app.models.storage.user_group import UserGroup


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[GroupRole]:
    """Every role assignment reaching the user through a group that is still valid."""
    result = await session.scalars(
        select(GroupRole)
        .join(UserGroup, UserGroup.id == GroupRole.group_id)
        .join(GroupMember, GroupMember.group_id == UserGroup.id)
        .where(
            GroupMember.user_id == user_id,
            or_(UserGroup.valid_until.is_(None), UserGroup.valid_until > now),
        )
    )
    return list(result)


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    role: RoleName,
    scope_kind: ScopeKind,
    scope_company_id: uuid.UUID | None,
    scope_domain_key: str | None,
) -> GroupRole:
    assignment = GroupRole(
        tenant_id=tenant_id,
        group_id=group_id,
        role=role,
        scope_kind=scope_kind,
        scope_company_id=scope_company_id,
        scope_domain_key=scope_domain_key,
    )
    session.add(assignment)
    await session.flush()
    return assignment
