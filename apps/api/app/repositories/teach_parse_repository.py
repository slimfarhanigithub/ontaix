"""Database access for the `teach_parse` table: parses recorded for usage learning."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ProposalOrigin
from app.models.storage.teach_parse import TeachParse


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    origin: ProposalOrigin,
    source_text: str,
    extractor: str,
    model_output: dict[str, Any],
) -> TeachParse:
    """Store one parse; `created_at` and `expires_at` come from the database defaults."""
    row = TeachParse(
        tenant_id=tenant_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        session_id=session_id,
        origin=origin,
        source_text=source_text,
        extractor=extractor,
        model_output=model_output,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, parse_id: uuid.UUID
) -> TeachParse | None:
    return await session.scalar(
        select(TeachParse).where(TeachParse.tenant_id == tenant_id, TeachParse.id == parse_id)
    )


async def get_unexpired(
    session: AsyncSession, tenant_id: uuid.UUID, parse_id: uuid.UUID
) -> TeachParse | None:
    return await session.scalar(
        select(TeachParse).where(
            TeachParse.tenant_id == tenant_id,
            TeachParse.id == parse_id,
            TeachParse.expires_at > func.now(),
        )
    )


async def delete_expired(session: AsyncSession) -> int:
    result = await session.execute(delete(TeachParse).where(TeachParse.expires_at < func.now()))
    return result.rowcount or 0


async def delete_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> int:
    result = await session.execute(
        delete(TeachParse).where(
            TeachParse.tenant_id == tenant_id, TeachParse.company_id == company_id
        )
    )
    return result.rowcount or 0
