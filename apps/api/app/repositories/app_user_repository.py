"""Database access for the `app_user` table."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
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


async def get(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> AppUser | None:
    return await session.scalar(
        select(AppUser)
        .where(AppUser.tenant_id == tenant_id, AppUser.id == user_id)
        .execution_options(populate_existing=True)
    )


async def email_taken(session: AsyncSession, tenant_id: uuid.UUID, email: str) -> bool:
    """True when a directory user of the organization already has this email, any case."""
    count = await session.scalar(
        select(func.count()).where(
            AppUser.tenant_id == tenant_id, func.lower(AppUser.email) == email.lower()
        )
    )
    return bool(count)


async def update_profile(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    values: dict[str, str | None],
) -> None:
    """Set `name` and/or `department`."""
    await session.execute(
        update(AppUser)
        .where(AppUser.tenant_id == tenant_id, AppUser.id == user_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def touch_login(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await session.execute(
        update(AppUser)
        .where(AppUser.tenant_id == tenant_id, AppUser.id == user_id)
        .values(last_login_at=func.now())
        .execution_options(synchronize_session=False)
    )
