"""Database access for the `outbox` table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ActorKind
from app.models.storage.outbox import Outbox


async def last_sequence(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """The highest outbox id of the tenant, or 0 before its first event."""
    value = await session.scalar(select(func.max(Outbox.id)).where(Outbox.tenant_id == tenant_id))
    return int(value or 0)


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Outbox]:
    result = await session.scalars(
        select(Outbox).where(Outbox.tenant_id == tenant_id).order_by(Outbox.id)
    )
    return list(result)


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    aggregate: str,
    action: str,
    subject: str,
    visibility: str,
    company_ids: list[uuid.UUID],
    domain_key: str | None,
    recipient_user_id: uuid.UUID | None = None,
    actor_kind: ActorKind,
    actor_id: uuid.UUID | None,
    bulk: bool,
    payload: dict[str, Any],
) -> Outbox:
    row = Outbox(
        tenant_id=tenant_id,
        aggregate=aggregate,
        action=action,
        subject=subject,
        visibility=visibility,
        company_ids=company_ids,
        domain_key=domain_key,
        recipient_user_id=recipient_user_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        bulk=bulk,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return row
