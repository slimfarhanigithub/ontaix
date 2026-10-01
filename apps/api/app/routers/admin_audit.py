"""`GET /admin/audit`: the platform audit log, newest first, super admin only."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.auth import PlatformAdminDependency, PlatformSessionDependency
from app.models.api.page import PageOf
from app.models.api.platform_audit import PlatformAuditEntry
from app.services import platform_audit_read_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Platform"])


@router.get("/audit", response_model=PageOf[PlatformAuditEntry])
async def list_platform_audit(
    request: Request, session: PlatformSessionDependency, _: PlatformAdminDependency
) -> PageOf[PlatformAuditEntry]:
    query = parse_list_query(request.query_params, platform_audit_read_service.FILTERABLE, ())
    return await platform_audit_read_service.list_entries(session, query)
