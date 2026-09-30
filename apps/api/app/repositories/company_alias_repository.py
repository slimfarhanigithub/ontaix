"""Database access for the `company_alias` table: misheard names and the labels meant.

Every read and write names the tenant and the company, so no query ever reaches another
company's aliases. One active alias per heard form: a new alias for a heard form retires the
active one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.company_alias import CompanyAlias

MAX_ACTIVE = 1000


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    heard: str,
    meant: str,
    concept_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
    at: datetime,
) -> CompanyAlias:
    """Store the alias; an active alias of the same heard form is retired first, unless it
    already means the same label, in which case it is kept and returned."""
    existing = await get_active_by_heard(session, tenant_id, company_id, heard)
    if existing is not None:
        if existing.meant.casefold() == meant.casefold():
            return existing
        existing.retired_at = at
        await session.flush()
    row = CompanyAlias(
        tenant_id=tenant_id,
        company_id=company_id,
        heard=heard,
        meant=meant,
        concept_id=concept_id,
        actor_user_id=actor_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, alias_id: uuid.UUID
) -> CompanyAlias | None:
    return await session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.tenant_id == tenant_id,
            CompanyAlias.company_id == company_id,
            CompanyAlias.id == alias_id,
        )
    )


async def get_active_by_heard(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, heard: str
) -> CompanyAlias | None:
    return await session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.tenant_id == tenant_id,
            CompanyAlias.company_id == company_id,
            CompanyAlias.retired_at.is_(None),
            func.lower(CompanyAlias.heard) == heard.lower(),
        )
    )


async def list_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> list[CompanyAlias]:
    """Every alias of the company, active and retired, newest first."""
    result = await session.scalars(
        select(CompanyAlias)
        .where(CompanyAlias.tenant_id == tenant_id, CompanyAlias.company_id == company_id)
        .order_by(CompanyAlias.created_at.desc(), CompanyAlias.id)
    )
    return list(result)


async def list_active(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, limit: int = MAX_ACTIVE
) -> list[CompanyAlias]:
    result = await session.scalars(
        select(CompanyAlias)
        .where(
            CompanyAlias.tenant_id == tenant_id,
            CompanyAlias.company_id == company_id,
            CompanyAlias.retired_at.is_(None),
        )
        .order_by(CompanyAlias.created_at.desc(), CompanyAlias.id)
        .limit(limit)
    )
    return list(result)


async def add_hits(session: AsyncSession, tenant_id: uuid.UUID, alias_ids: list[uuid.UUID]) -> None:
    if not alias_ids:
        return
    await session.execute(
        update(CompanyAlias)
        .where(CompanyAlias.tenant_id == tenant_id, CompanyAlias.id.in_(alias_ids))
        .values(hits=CompanyAlias.hits + 1)
        .execution_options(synchronize_session=False)
    )


async def retire_by_concepts(
    session: AsyncSession, tenant_id: uuid.UUID, concept_ids: list[uuid.UUID], at: datetime
) -> int:
    """Retire every active alias of the tenant linked to one of `concept_ids`."""
    if not concept_ids:
        return 0
    result = await session.execute(
        update(CompanyAlias)
        .where(
            CompanyAlias.tenant_id == tenant_id,
            CompanyAlias.retired_at.is_(None),
            CompanyAlias.concept_id.in_(concept_ids),
        )
        .values(retired_at=at)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


async def retire_over_cap(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, cap: int, at: datetime
) -> int:
    """Retire the oldest active aliases of the company beyond `cap`; returns how many."""
    excess = await session.scalars(
        select(CompanyAlias.id)
        .where(
            CompanyAlias.tenant_id == tenant_id,
            CompanyAlias.company_id == company_id,
            CompanyAlias.retired_at.is_(None),
        )
        .order_by(CompanyAlias.created_at.desc(), CompanyAlias.id)
        .offset(cap)
    )
    ids = list(excess)
    if not ids:
        return 0
    await session.execute(
        update(CompanyAlias)
        .where(CompanyAlias.id.in_(ids))
        .values(retired_at=at)
        .execution_options(synchronize_session=False)
    )
    return len(ids)


async def delete(session: AsyncSession, alias: CompanyAlias) -> None:
    await session.delete(alias)
    await session.flush()


async def delete_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> int:
    result = await session.execute(
        delete_rows(CompanyAlias).where(
            CompanyAlias.tenant_id == tenant_id, CompanyAlias.company_id == company_id
        )
    )
    return result.rowcount or 0


async def delete_retired_before(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(
        delete_rows(CompanyAlias).where(CompanyAlias.retired_at < cutoff)
    )
    return result.rowcount or 0
