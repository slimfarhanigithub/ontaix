"""Database access for the append-only `platform_audit_entry` table (platform role only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.platform_audit_entry import PlatformAuditEntry


@dataclass(frozen=True)
class PlatformAuditFilter:
    actions: list[str] | None = None
    ok: bool | None = None
    tenant_ids: list[uuid.UUID] | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = None


async def create(
    session: AsyncSession,
    *,
    action: str,
    ok: bool,
    what: str,
    actor_account_id: uuid.UUID | None,
    target_tenant_id: uuid.UUID | None,
    target_account_id: uuid.UUID | None,
    client_ip: str | None,
) -> PlatformAuditEntry:
    entry = PlatformAuditEntry(
        action=action,
        ok=ok,
        what=what,
        actor_account_id=actor_account_id,
        target_tenant_id=target_tenant_id,
        target_account_id=target_account_id,
        client_ip=client_ip,
    )
    session.add(entry)
    await session.flush()
    return entry


async def page(
    session: AsyncSession, where: PlatformAuditFilter, offset: int, limit: int
) -> tuple[list[PlatformAuditEntry], int]:
    """One page, newest first, and the total that matches."""
    query = _filtered(select(PlatformAuditEntry), where)
    total = await session.scalar(_filtered(select(func.count(PlatformAuditEntry.id)), where))
    rows = await session.scalars(
        query.order_by(PlatformAuditEntry.id.desc()).offset(offset).limit(limit)
    )
    return list(rows), int(total or 0)


async def latest(
    session: AsyncSession, action: str, actor_account_id: uuid.UUID, tenant_id: uuid.UUID
) -> PlatformAuditEntry | None:
    return await session.scalar(
        select(PlatformAuditEntry)
        .where(
            PlatformAuditEntry.action == action,
            PlatformAuditEntry.actor_account_id == actor_account_id,
            PlatformAuditEntry.target_tenant_id == tenant_id,
        )
        .order_by(PlatformAuditEntry.id.desc())
        .limit(1)
    )


def _filtered[S: Select](query: S, where: PlatformAuditFilter) -> S:
    if where.actions:
        query = query.where(PlatformAuditEntry.action.in_(where.actions))
    if where.ok is not None:
        query = query.where(PlatformAuditEntry.ok.is_(where.ok))
    if where.tenant_ids:
        query = query.where(PlatformAuditEntry.target_tenant_id.in_(where.tenant_ids))
    if where.since is not None:
        query = query.where(PlatformAuditEntry.at >= where.since)
    if where.until is not None:
        query = query.where(PlatformAuditEntry.at <= where.until)
    if where.q:
        pattern = f"%{_escape_like(where.q)}%"
        query = query.where(
            or_(
                PlatformAuditEntry.what.ilike(pattern, escape="\\"),
                PlatformAuditEntry.action.ilike(pattern, escape="\\"),
            )
        )
    return query


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
