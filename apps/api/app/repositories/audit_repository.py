"""Database access for the append-only `audit_entry` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import ActorKind


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[AuditEntry]:
    result = await session.scalars(
        select(AuditEntry).where(AuditEntry.tenant_id == tenant_id).order_by(AuditEntry.id.desc())
    )
    return list(result)


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_kind: ActorKind,
    actor_user_id: uuid.UUID | None,
    kind: str,
    what: str,
    ok: bool,
    proposal_id: uuid.UUID | None,
    company_ids: list[uuid.UUID],
) -> AuditEntry:
    entry = AuditEntry(
        tenant_id=tenant_id,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        kind=kind,
        what=what,
        ok=ok,
        proposal_id=proposal_id,
        company_ids=company_ids,
    )
    session.add(entry)
    await session.flush()
    return entry
