"""Database access for the `company` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.company import Company


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Company]:
    result = await session.scalars(
        select(Company).where(Company.tenant_id == tenant_id).order_by(Company.position)
    )
    return list(result)


async def get(session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID) -> Company | None:
    return await session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id)
    )


async def get_by_key(session: AsyncSession, tenant_id: uuid.UUID, key: str) -> Company | None:
    return await session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.key == key)
    )


async def next_position(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(Company.position)).where(Company.tenant_id == tenant_id)
    )
    return 0 if current is None else current + 1


async def create(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    key: str,
    name: str,
    sub: str,
    position: int,
    is_home: bool,
) -> Company:
    company = Company(
        tenant_id=tenant_id, key=key, name=name, sub=sub, position=position, is_home=is_home
    )
    session.add(company)
    await session.flush()
    return company


async def delete(session: AsyncSession, company: Company) -> None:
    await session.delete(company)
    await session.flush()


async def mark_dying(session: AsyncSession, company: Company, at: datetime) -> None:
    """Stamp the moment the company starts dying; it is deleted later in the same transaction."""
    company.dying_at = at
    await session.flush()
