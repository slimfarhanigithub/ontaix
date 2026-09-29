"""Database access for the `llm_call` table: one cost record per language model call."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    """
    INSERT INTO ontaix.llm_call (
        tenant_id, actor_kind, actor_id, company_id, purpose, provider, model, input_tokens,
        output_tokens, cost_eur, latency_ms, pages, outcome)
    VALUES (:tenant_id, CAST(:actor_kind AS ontaix.actor_kind), :actor_id, :company_id, :purpose,
        :provider, :model, :input_tokens, :output_tokens, :cost_eur, :latency_ms, :pages,
        :outcome)
    """
)

_TOTALS = text(
    """
    SELECT purpose, count(*) AS calls, coalesce(sum(input_tokens), 0) AS input_tokens,
        coalesce(sum(output_tokens), 0) AS output_tokens, coalesce(sum(cost_eur), 0) AS cost_eur,
        sum(pages) AS pages
    FROM ontaix.llm_call
    WHERE tenant_id = :tenant_id AND occurred_at >= :start AND occurred_at < :end
    GROUP BY purpose ORDER BY purpose
    """
)


@dataclass(frozen=True)
class PurposeTotals:
    purpose: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_eur: float
    # Set for the purpose `document_ocr` only.
    pages: int | None = None


@dataclass(frozen=True)
class CallRecord:
    tenant_id: uuid.UUID
    actor_kind: str
    actor_id: uuid.UUID
    company_id: uuid.UUID | None
    purpose: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_ms: int
    outcome: str
    # Set exactly for the purpose `document_ocr`: the pages the provider processed.
    pages: int | None = None


async def insert(session: AsyncSession, record: CallRecord) -> None:
    await session.execute(_INSERT, record.__dict__)


async def totals_by_purpose(
    session: AsyncSession, tenant_id: uuid.UUID, start: datetime, end: datetime
) -> list[PurposeTotals]:
    rows = (
        await session.execute(_TOTALS, {"tenant_id": tenant_id, "start": start, "end": end})
    ).all()
    return [
        PurposeTotals(
            r.purpose,
            int(r.calls),
            int(r.input_tokens),
            int(r.output_tokens),
            float(r.cost_eur),
            int(r.pages) if r.pages is not None else None,
        )
        for r in rows
    ]


async def delete_older_than(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(
        text("DELETE FROM ontaix.llm_call WHERE occurred_at < :cutoff"), {"cutoff": cutoff}
    )
    return result.rowcount or 0
