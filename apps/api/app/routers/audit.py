"""GET /audit: the append-only audit log, newest first."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.auth import CallerDependency, SessionDependency
from app.models.api.audit import AuditEntry
from app.models.api.page import PageOf
from app.services import audit_read_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audit"])


@router.get("/audit", response_model=PageOf[AuditEntry])
async def list_audit(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> PageOf[AuditEntry]:
    query = parse_list_query(
        request.query_params, audit_read_service.FILTERABLE, audit_read_service.SORTABLE
    )
    return await audit_read_service.list_audit(session, caller, query)
