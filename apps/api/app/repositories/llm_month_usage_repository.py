"""Database access for the `llm_month_usage` table: tokens and OCR pages counted against the
monthly caps."""

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

_RESERVE_PAGES = text(
    """
    INSERT INTO ontaix.llm_month_usage AS u (tenant_id, month, ocr_pages)
    SELECT :tenant_id, :month, CAST(:pages AS integer)
    WHERE CAST(:pages AS integer) <= CAST(:cap AS integer)
    ON CONFLICT (tenant_id, month)
    DO UPDATE SET ocr_pages = u.ocr_pages + EXCLUDED.ocr_pages
    WHERE u.ocr_pages + EXCLUDED.ocr_pages <= CAST(:cap AS integer)
    RETURNING u.ocr_pages
    """
)

_SETTLE_PAGES = text(
    """
    UPDATE ontaix.llm_month_usage
    SET ocr_pages = greatest(ocr_pages + CAST(:actual AS integer) - CAST(:reserved AS integer), 0)
    WHERE tenant_id = :tenant_id AND month = :month
    """
)

_PAGES = text(
    "SELECT ocr_pages FROM ontaix.llm_month_usage WHERE tenant_id = :tenant_id AND month = :month"
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


async def reserve_pages(
    session: AsyncSession, tenant_id: uuid.UUID, month: date, pages: int, cap: int
) -> int | None:
    """Count `pages` OCR pages for the month in one conditional upsert; None when the page cap
    would pass."""
    result = await session.execute(
        _RESERVE_PAGES, {"tenant_id": tenant_id, "month": month, "pages": pages, "cap": cap}
    )
    return result.scalar_one_or_none()


async def settle_pages(
    session: AsyncSession, tenant_id: uuid.UUID, month: date, reserved: int, actual: int
) -> None:
    """Replace a page reservation by the pages processed, in the month it was made in."""
    await session.execute(
        _SETTLE_PAGES,
        {"tenant_id": tenant_id, "month": month, "reserved": reserved, "actual": actual},
    )


async def pages_for(session: AsyncSession, tenant_id: uuid.UUID, month: date) -> int:
    result = await session.execute(_PAGES, {"tenant_id": tenant_id, "month": month})
    return int(result.scalar_one_or_none() or 0)
