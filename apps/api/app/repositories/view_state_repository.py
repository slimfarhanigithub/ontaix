"""Database access for the `tenant_view_state` table."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant_view_state import TenantViewState


async def get(session: AsyncSession, tenant_id: uuid.UUID) -> TenantViewState | None:
    return await session.get(TenantViewState, tenant_id)


async def create(session: AsyncSession, tenant_id: uuid.UUID) -> TenantViewState:
    state = TenantViewState(tenant_id=tenant_id)
    session.add(state)
    await session.flush()
    return state
