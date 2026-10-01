"""Read-only support sessions: open one in an organization, or end the current one."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, Response

from app.auth import PlatformAdminDependency, PlatformSessionDependency, set_session_cookie
from app.models.api.organization_user import SupportSessionStart
from app.models.api.session import Session
from app.services import session_service, support_session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Platform"])


@router.post("/organizations/{organization_id}/support-session", response_model=Session)
async def start_support_session(
    organization_id: uuid.UUID,
    body: SupportSessionStart,
    request: Request,
    response: Response,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Session:
    issued = await support_session_service.start(
        session, admin, organization_id, body.reason, request.headers.get("user-agent")
    )
    set_session_cookie(response, issued.token)
    return issued.session


@router.delete("/support-session", response_model=Session)
async def end_support_session(
    request: Request,
    response: Response,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Session:
    issued = await support_session_service.end(session, admin, request.headers.get("user-agent"))
    if issued is None:
        return await session_service.describe(session, admin.live.row, admin.live.account)
    set_session_cookie(response, issued.token)
    return issued.session
