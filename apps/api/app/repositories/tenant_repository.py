"""Database access for the `tenant` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant import Tenant
from app.repositories import tenant_domain_repository


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    return await session.scalar(select(Tenant).where(Tenant.slug == slug))


async def get(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def create(session: AsyncSession, slug: str, name: str) -> Tenant:
    """The tenant row with its nine template domains copied into `tenant_domain`."""
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.flush()
    await tenant_domain_repository.copy_templates(session, tenant.id)
    return tenant
