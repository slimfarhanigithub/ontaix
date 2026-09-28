"""Database access for the `app_user` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.app_user import AppUser


async def get_by_identity(session: AsyncSession, issuer: str, subject: str) -> AppUser | None:
    return await session.scalar(
        select(AppUser).where(AppUser.issuer == issuer, AppUser.subject == subject)
    )


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[AppUser]:
    result = await session.scalars(select(AppUser).where(AppUser.tenant_id == tenant_id))
    return list(result)


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    issuer: str,
    subject: str,
    email: str,
    name: str,
    department: str | None,
    company_id: uuid.UUID | None,
) -> AppUser:
    user = AppUser(
        tenant_id=tenant_id,
        issuer=issuer,
        subject=subject,
        email=email,
        name=name,
        department=department,
        company_id=company_id,
    )
    session.add(user)
    await session.flush()
    return user
