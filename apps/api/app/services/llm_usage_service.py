"""Tokens and cost records of Ontaix's own language model calls.

A call reserves its upper bound (estimated input plus the maximum output tokens) against the
tenant's monthly cap before it starts, in a short transaction of its own that commits before the
provider is called, so no row lock is held during the call. After the call, in another short
transaction, the reservation is settled to the actual count in the month it was made in and one
`llm_call` cost record is inserted. The record holds counts, cost, latency and outcome only -
never the sentence, the prompt, the answer or a credential.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.clients.db_client import get_session_factory
from app.models.api.cost import LlmPurposeUsage, LlmUsage
from app.repositories import llm_call_repository, llm_month_usage_repository
from app.repositories.llm_call_repository import CallRecord
from app.utilities.clock import get_clock

logger = logging.getLogger(__name__)

TEACH_EXTRACTION = "teach_extraction"
DOCUMENT_OCR = "document_ocr"
RETENTION = timedelta(days=400)


@dataclass(frozen=True)
class Reservation:
    """Units counted against a monthly cap: tokens, or OCR pages for a page reservation."""

    tenant_id: uuid.UUID
    month: date
    tokens: int


async def reserve(tenant_id: uuid.UUID, tokens: int, cap: int) -> Reservation | None:
    """Count `tokens` against this month's cap and commit; None when the cap would pass."""
    month = month_of(get_clock().now())
    async with get_session_factory()() as session:
        counted = await llm_month_usage_repository.reserve(session, tenant_id, month, tokens, cap)
        await session.commit()
    return Reservation(tenant_id, month, tokens) if counted is not None else None


async def settle(reservation: Reservation, record: CallRecord) -> None:
    """Settle the reservation to the call's actual tokens and store its cost record."""
    actual = record.input_tokens + record.output_tokens
    async with get_session_factory()() as session:
        await llm_month_usage_repository.settle(
            session, reservation.tenant_id, reservation.month, reservation.tokens, actual
        )
        await llm_call_repository.insert(session, record)
        await session.commit()


async def reserve_pages(tenant_id: uuid.UUID, pages: int, cap: int) -> Reservation | None:
    """Count OCR `pages` against this month's page cap and commit; None when it would pass."""
    month = month_of(get_clock().now())
    async with get_session_factory()() as session:
        counted = await llm_month_usage_repository.reserve_pages(
            session, tenant_id, month, pages, cap
        )
        await session.commit()
    return Reservation(tenant_id, month, pages) if counted is not None else None


async def settle_pages(reservation: Reservation, record: CallRecord) -> None:
    """Settle a page reservation to the pages the provider processed and store the cost record."""
    async with get_session_factory()() as session:
        await llm_month_usage_repository.settle_pages(
            session, reservation.tenant_id, reservation.month, reservation.tokens, record.pages or 0
        )
        await llm_call_repository.insert(session, record)
        await session.commit()


async def month_usage(tenant_id: uuid.UUID, month: date, cap: int, page_cap: int) -> LlmUsage:
    """The month's calls, tokens, OCR pages and estimated cost, by purpose."""
    start = datetime(month.year, month.month, 1, tzinfo=get_clock().now().tzinfo)
    end = _next_month(start)
    async with get_session_factory()() as session:
        totals = await llm_call_repository.totals_by_purpose(session, tenant_id, start, end)
        counted = await llm_month_usage_repository.tokens_for(session, tenant_id, month)
        pages = await llm_month_usage_repository.pages_for(session, tenant_id, month)
    return LlmUsage(
        calls=sum(t.calls for t in totals),
        input_tokens=sum(t.input_tokens for t in totals),
        output_tokens=sum(t.output_tokens for t in totals),
        tokens_used=counted,
        token_cap=cap,
        ocr_pages_used=pages,
        ocr_page_cap=page_cap,
        cost_eur=round(sum(t.cost_eur for t in totals), 6),
        by_purpose=[
            LlmPurposeUsage(
                purpose=t.purpose, calls=t.calls, pages=t.pages, cost_eur=round(t.cost_eur, 6)
            )
            for t in totals
        ],
    )


async def purge_old_calls() -> int:
    """Delete cost records older than 400 days, across tenants, in its own transaction."""
    async with get_session_factory()() as session:
        deleted = await llm_call_repository.delete_older_than(
            session, get_clock().now() - RETENTION
        )
        await session.commit()
    return deleted


def month_of(at: datetime) -> date:
    return date(at.year, at.month, 1)


def _next_month(start: datetime) -> datetime:
    return (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
