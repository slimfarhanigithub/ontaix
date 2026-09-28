"""Database access for the `connector_type` reference table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.connector_type import ConnectorType


async def list_in_catalogue_order(session: AsyncSession) -> list[ConnectorType]:
    result = await session.scalars(select(ConnectorType).order_by(ConnectorType.position))
    return list(result)
