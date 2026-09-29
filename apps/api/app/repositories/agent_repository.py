"""Database access for the `agent` table."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_COUNTS = text(
    """
    SELECT count(*) AS registered, count(*) FILTER (WHERE access) AS with_access
    FROM ontaix.agent WHERE tenant_id = :tenant_id
    """
)


@dataclass(frozen=True)
class AgentCounts:
    registered: int
    with_access: int


async def counts(session: AsyncSession, tenant_id: uuid.UUID) -> AgentCounts:
    row = (await session.execute(_COUNTS, {"tenant_id": tenant_id})).one()
    return AgentCounts(int(row.registered), int(row.with_access))
