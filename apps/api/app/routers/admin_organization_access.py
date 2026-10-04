"""Platform access: a super admin enters an organization to act inside it, or leaves it."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, Response

from app.auth import PlatformAdminDependency, PlatformSessionDependency, set_session_cookie
from app.models.api.session import Session
from app.services import organization_access_service, session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Platform"])


@router.post("/organizations/{organization_id}/enter", response_model=Session)
async def enter_organization(
    organization_id: uuid.UUID,
    request: Request,
    response: Response,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Session:
    issued = await organization_access_service.enter(
        session, admin, organization_id, request.headers.get("user-agent")
    )
    set_session_cookie(response, issued.token)
    return issued.session


@router.post("/exit", response_model=Session)
async def exit_organization(
    request: Request,
    response: Response,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Session:
    issued = await organization_access_service.leave(
        session, admin, request.headers.get("user-agent")
    )
    if issued is None:
        return await session_service.describe(session, admin.live.row, admin.live.account)
    set_session_cookie(response, issued.token)
    return issued.session
