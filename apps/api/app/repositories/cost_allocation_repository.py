"""Database access for the `cost_allocation` table."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ALLOCATED = text(
    "SELECT allocated_eur FROM ontaix.cost_allocation WHERE tenant_id = :tenant_id"
    " AND month = :month"
)


async def allocated_eur(session: AsyncSession, tenant_id: uuid.UUID, month: date) -> float:
    value = (await session.execute(_ALLOCATED, {"tenant_id": tenant_id, "month": month})).scalar()
    return float(value or 0)
