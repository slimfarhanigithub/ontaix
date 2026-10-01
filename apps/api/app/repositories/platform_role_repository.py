"""Database access for the `platform_role_assignment` table.

Only the schema owner may write it; the admin CLI is the one writer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import PlatformRoleName
from app.models.storage.platform_role_assignment import PlatformRoleAssignment


async def roles_of(session: AsyncSession, account_id: uuid.UUID) -> list[PlatformRoleName]:
    rows = await session.scalars(
        select(PlatformRoleAssignment.role).where(PlatformRoleAssignment.account_id == account_id)
    )
    return list(rows)


async def grant(
    session: AsyncSession,
    account_id: uuid.UUID,
    role: PlatformRoleName,
    granted_by: uuid.UUID | None,
) -> None:
    session.add(PlatformRoleAssignment(account_id=account_id, role=role, granted_by=granted_by))
    await session.flush()
