"""The platform audit log page of the super admin: newest first, filterable by action, outcome,
organization and time window."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.organization import OrganizationRef
from app.models.api.page import PageOf
from app.models.api.platform_audit import PlatformActor, PlatformAuditEntry
from app.repositories import account_repository, platform_audit_repository, tenant_repository
from app.repositories.platform_audit_repository import PlatformAuditFilter
from app.utilities.listing import ListQuery
from app.utilities.problems import bad_request

logger = logging.getLogger(__name__)

FILTERABLE = ("action", "ok", "organizationId", "from", "to")
TIME_BOUND_DETAIL = "from and to must be ISO 8601 timestamps with a UTC offset"


async def list_entries(session: AsyncSession, query: ListQuery) -> PageOf[PlatformAuditEntry]:
    where = PlatformAuditFilter(
        actions=query.filters.get("action"),
        ok=_ok(query.filters.get("ok")),
        tenant_ids=_ids(query.filters.get("organizationId")),
        since=_time_bound(query.filters.get("from")),
        until=_time_bound(query.filters.get("to")),
        q=query.q,
    )
    rows, total = await platform_audit_repository.page(
        session, where, (query.page - 1) * query.page_size, query.page_size
    )
    accounts = {
        a.id: a
        for a in await account_repository.list_by_ids(
            session, {r.actor_account_id for r in rows if r.actor_account_id}
        )
    }
    tenants = {
        t.id: t
        for t in await tenant_repository.list_by_ids(
            session, {r.target_tenant_id for r in rows if r.target_tenant_id}
        )
    }
    items = []
    for r in rows:
        actor = accounts.get(r.actor_account_id) if r.actor_account_id else None
        tenant = tenants.get(r.target_tenant_id) if r.target_tenant_id else None
        items.append(
            PlatformAuditEntry(
                id=r.id,
                at=r.at,
                actor=PlatformActor(account_id=actor.id, email=actor.email) if actor else None,
                action=r.action,
                ok=r.ok,
                organization=(
                    OrganizationRef(id=tenant.id, name=tenant.name, slug=tenant.slug)
                    if tenant
                    else None
                ),
                target_account_id=r.target_account_id,
                what=r.what,
                client_ip=str(r.client_ip) if r.client_ip else None,
            )
        )
    return PageOf[PlatformAuditEntry](
        items=items, page=query.page, page_size=query.page_size, total=total
    )


def _ok(values: list[str] | None) -> bool | None:
    if not values or len(values) != 1:
        return None
    value = values[0].lower()
    if value not in {"true", "false"}:
        raise bad_request("ok must be true or false")
    return value == "true"


def _ids(values: list[str] | None) -> list[uuid.UUID] | None:
    if not values:
        return None
    try:
        return [uuid.UUID(v) for v in values]
    except ValueError as exc:
        raise bad_request("organizationId must be an organization id") from exc


def _time_bound(values: list[str] | None) -> datetime | None:
    if not values:
        return None
    try:
        bound = datetime.fromisoformat(values[0])
    except ValueError as exc:
        raise bad_request(TIME_BOUND_DETAIL) from exc
    if bound.tzinfo is None or bound.utcoffset() is None:
        raise bad_request(TIME_BOUND_DETAIL)
    return bound
