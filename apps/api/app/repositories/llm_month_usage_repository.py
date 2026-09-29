"""Database access for the `llm_month_usage` table: tokens counted against the monthly cap."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_RESERVE = text(
    """
    INSERT INTO ontaix.llm_month_usage AS u (tenant_id, month, tokens)
    SELECT :tenant_id, :month, CAST(:reserve AS bigint)
    WHERE CAST(:reserve AS bigint) <= CAST(:cap AS bigint)
    ON CONFLICT (tenant_id, month)
    DO UPDATE SET tokens = u.tokens + EXCLUDED.tokens
    WHERE u.tokens + EXCLUDED.tokens <= CAST(:cap AS bigint)
    RETURNING u.tokens
    """
)

_SETTLE = text(
    """
    UPDATE ontaix.llm_month_usage
    SET tokens = greatest(tokens + CAST(:actual AS bigint) - CAST(:reserved AS bigint), 0)
    WHERE tenant_id = :tenant_id AND month = :month
    """
)

_TOKENS = text(
    "SELECT tokens FROM ontaix.llm_month_usage WHERE tenant_id = :tenant_id AND month = :month"
)


async def reserve(
    session: AsyncSession, tenant_id: uuid.UUID, month: date, tokens: int, cap: int
) -> int | None:
    """Count `tokens` for the month in one conditional upsert; None when the cap would pass."""
    result = await session.execute(
        _RESERVE, {"tenant_id": tenant_id, "month": month, "reserve": tokens, "cap": cap}
    )
    return result.scalar_one_or_none()


async def settle(
    session: AsyncSession, tenant_id: uuid.UUID, month: date, reserved: int, actual: int
) -> None:
    """Replace a reservation by the actual count, in the month it was made in."""
    await session.execute(
        _SETTLE,
        {"tenant_id": tenant_id, "month": month, "reserved": reserved, "actual": actual},
    )


async def tokens_for(session: AsyncSession, tenant_id: uuid.UUID, month: date) -> int:
    result = await session.execute(_TOKENS, {"tenant_id": tenant_id, "month": month})
    return int(result.scalar_one_or_none() or 0)
