"""Database access for the `rate_budget_window` table: per-actor hourly budgets."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CHARGE = text(
    """
    INSERT INTO ontaix.rate_budget_window AS w
        (tenant_id, actor_kind, actor_id, budget, window_start, spent)
    SELECT :tenant_id, CAST(:actor_kind AS ontaix.actor_kind), :actor_id, :budget,
        :window_start,
        CAST(:units AS integer)
    WHERE CAST(:units AS integer) <= CAST(:limit AS integer)
    ON CONFLICT (tenant_id, actor_kind, actor_id, budget, window_start)
    DO UPDATE SET spent = w.spent + EXCLUDED.spent
    WHERE w.spent + EXCLUDED.spent <= CAST(:limit AS integer)
    RETURNING w.spent
    """
)


async def charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_kind: str,
    actor_id: uuid.UUID,
    budget: str,
    window_start: datetime,
    units: int,
    limit: int,
) -> int | None:
    """Spend `units` in one conditional upsert; the new total, or None when it would pass
    `limit`."""
    result = await session.execute(
        _CHARGE,
        {
            "tenant_id": tenant_id,
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "budget": budget,
            "window_start": window_start,
            "units": units,
            "limit": limit,
        },
    )
    return result.scalar_one_or_none()


async def delete_started_before(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(
        text("DELETE FROM ontaix.rate_budget_window WHERE window_start < :cutoff"),
        {"cutoff": cutoff},
    )
    return result.rowcount or 0
