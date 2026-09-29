"""Database access for the `agent_month_usage` table: agent reads and cost per month."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BY_PLATFORM = text(
    """
    SELECT a.platform, count(*) AS agents, coalesce(sum(u.reads), 0) AS reads,
        coalesce(sum(u.cost_eur), 0) AS cost_eur
    FROM ontaix.agent a
    LEFT JOIN ontaix.agent_month_usage u ON u.agent_id = a.id AND u.month = :month
    WHERE a.tenant_id = :tenant_id AND a.access
    GROUP BY a.platform
    ORDER BY cost_eur DESC, a.platform
    """
)


@dataclass(frozen=True)
class PlatformUsage:
    platform: str
    agents_with_access: int
    reads: int
    cost_eur: float


async def by_platform(
    session: AsyncSession, tenant_id: uuid.UUID, month: date
) -> list[PlatformUsage]:
    """Reads and cost of the agents with access, per platform, most expensive first."""
    rows = (await session.execute(_BY_PLATFORM, {"tenant_id": tenant_id, "month": month})).all()
    return [PlatformUsage(r.platform, int(r.agents), int(r.reads), float(r.cost_eur)) for r in rows]
