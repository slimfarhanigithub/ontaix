"""Database access for the `tenant` table (an organization)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant import Tenant


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    return await session.scalar(select(Tenant).where(Tenant.slug == slug))


async def get(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id, populate_existing=True)


async def get_by_name(session: AsyncSession, name: str) -> Tenant | None:
    """The tenant with this name, compared case-insensitively."""
    return await session.scalar(select(Tenant).where(func.lower(Tenant.name) == name.lower()))


async def list_all(session: AsyncSession) -> list[Tenant]:
    """Every tenant, for the platform portal; readable only through the platform role."""
    return list(await session.scalars(select(Tenant).order_by(Tenant.created_at, Tenant.id)))


async def list_by_ids(session: AsyncSession, ids: set[uuid.UUID]) -> list[Tenant]:
    if not ids:
        return []
    return list(await session.scalars(select(Tenant).where(Tenant.id.in_(ids))))


async def slug_exists(session: AsyncSession, slug: str) -> bool:
    return await session.scalar(select(func.count()).where(Tenant.slug == slug)) > 0


async def create(session: AsyncSession, slug: str, name: str) -> Tenant:
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.flush()
    return tenant


async def rename(session: AsyncSession, tenant_id: uuid.UUID, name: str) -> None:
    await session.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(name=name, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def set_disabled(session: AsyncSession, tenant_id: uuid.UUID, disabled: bool) -> bool:
    """Disable or enable; False when the tenant already was in that state."""
    condition = Tenant.disabled_at.is_(None) if disabled else Tenant.disabled_at.is_not(None)
    result = await session.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id, condition)
        .values(disabled_at=func.now() if disabled else None, updated_at=func.now())
        .returning(Tenant.id)
        .execution_options(synchronize_session=False)
    )
    changed = result.first() is not None
    return changed
