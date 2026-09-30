"""Database access for the `organization_settings` table."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import CompanyMode
from app.models.storage.organization_settings import OrganizationSettings


async def get(session: AsyncSession, tenant_id: uuid.UUID) -> OrganizationSettings | None:
    return await session.get(OrganizationSettings, tenant_id, populate_existing=True)


async def company_mode(session: AsyncSession, tenant_id: uuid.UUID) -> CompanyMode:
    """The organization's company mode; `multiple` for a tenant without the row."""
    row = await get(session, tenant_id)
    return row.company_mode if row is not None else CompanyMode.MULTIPLE


async def create(
    session: AsyncSession, tenant_id: uuid.UUID, mode: CompanyMode
) -> OrganizationSettings:
    row = OrganizationSettings(tenant_id=tenant_id, company_mode=mode)
    session.add(row)
    await session.flush()
    return row


async def set_company_mode(session: AsyncSession, tenant_id: uuid.UUID, mode: CompanyMode) -> None:
    """Set the mode; the database trigger refuses `single` while two or more companies exist."""
    await session.execute(
        update(OrganizationSettings)
        .where(OrganizationSettings.tenant_id == tenant_id)
        .values(company_mode=mode, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def modes(session: AsyncSession) -> dict[uuid.UUID, CompanyMode]:
    """Every organization's company mode, for the platform portal (platform role)."""
    rows = await session.execute(
        select(OrganizationSettings.tenant_id, OrganizationSettings.company_mode)
    )
    return {tenant_id: mode for tenant_id, mode in rows.all()}
