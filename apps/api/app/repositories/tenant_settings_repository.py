"""Database access for the `tenant_settings` table."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant_settings import TenantSettings


async def get(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettings | None:
    return await session.get(TenantSettings, tenant_id, populate_existing=True)


async def create(session: AsyncSession, tenant_id: uuid.UUID, **values: object) -> TenantSettings:
    settings = TenantSettings(tenant_id=tenant_id, **values)
    session.add(settings)
    await session.flush()
    return settings


async def set_color(
    session: AsyncSession, settings: TenantSettings, domain_key: str, color: str
) -> None:
    """Write the tenant-wide colour override of one domain into the appearance colours."""
    settings.colors = {**(settings.colors or {}), domain_key: color}
    await session.flush()
