"""The Audit log page: newest first, filterable by kind, outcome, actor kind and time window.

An entry is listed, and counted in `total`, only when the caller holds `audit.read` in a scope
that contains every company the entry names, or on the domain scope named by the entry's
`domain_key`; an entry naming no company is tenant-wide.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.audit import AuditEntry as AuditEntryDto
from app.models.api.page import PageOf
from app.repositories import app_user_repository, audit_repository
from app.services import audit_service
from app.utilities.listing import ListQuery, matches_search, paginate
from app.utilities.permissions import can_read_audit, can_read_audit_entry
from app.utilities.problems import bad_request, forbidden

logger = logging.getLogger(__name__)

FILTERABLE = ("kind", "ok", "actorKind", "from", "to")
SORTABLE = ("at",)
TIME_BOUND_DETAIL = "from and to must be ISO 8601 timestamps with a UTC offset"


async def list_audit(
    session: AsyncSession, caller: Caller, query: ListQuery
) -> PageOf[AuditEntryDto]:
    if not can_read_audit(caller.grants):
        raise forbidden("reading the audit log requires Administrator, Governor or Auditor")
    entries = await audit_repository.list_for_tenant(session, caller.tenant_id)
    names = audit_service.user_names(
        await app_user_repository.list_for_tenant(session, caller.tenant_id)
    )
    since = _time_bound(query.filters.get("from"))
    until = _time_bound(query.filters.get("to"))
    rows = []
    for entry in entries:
        if not can_read_audit_entry(caller.grants, entry.company_ids, entry.domain_key):
            continue
        if "kind" in query.filters and entry.kind not in query.filters["kind"]:
            continue
        if "ok" in query.filters and str(entry.ok).lower() not in [
            v.lower() for v in query.filters["ok"]
        ]:
            continue
        if (
            "actorKind" in query.filters
            and entry.actor_kind.value not in query.filters["actorKind"]
        ):
            continue
        if since and entry.at < since:
            continue
        if until and entry.at > until:
            continue
        if not matches_search(query.q, entry.kind, entry.what):
            continue
        rows.append(entry)
    ordered = ListQuery(
        page=query.page,
        page_size=query.page_size,
        q=query.q,
        filters=query.filters,
        sort="at",
        order="desc" if query.sort is None else query.order,
    )
    page, total = paginate(rows, ordered, {"at": lambda e: e.id}, "at")
    return PageOf[AuditEntryDto](
        items=[audit_service.to_dto(e, names) for e in page],
        page=query.page,
        page_size=query.page_size,
        total=total,
    )


def _time_bound(values: list[str] | None) -> datetime | None:
    """Parse `from` or `to`; the value must carry its UTC offset to compare with entry times."""
    if not values:
        return None
    try:
        bound = datetime.fromisoformat(values[0])
    except ValueError as exc:
        raise bad_request(TIME_BOUND_DETAIL) from exc
    if bound.tzinfo is None or bound.utcoffset() is None:
        raise bad_request(TIME_BOUND_DETAIL)
    return bound
