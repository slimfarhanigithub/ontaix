"""`/admin/organizations/{organizationId}/users`: an organization's accounts, super admin only."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, Response, status

from app.auth import PlatformAdminDependency, PlatformSessionDependency
from app.models.api.organization_user import (
    OrganizationUser,
    OrganizationUserCreate,
    OrganizationUserUpdate,
    PasswordReset,
)
from app.models.api.page import PageOf
from app.services import organization_user_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/organizations/{organization_id}/users", tags=["Platform"])


@router.get("", response_model=PageOf[OrganizationUser])
async def list_users(
    organization_id: uuid.UUID,
    request: Request,
    session: PlatformSessionDependency,
    _: PlatformAdminDependency,
) -> PageOf[OrganizationUser]:
    query = parse_list_query(
        request.query_params,
        organization_user_service.FILTERABLE,
        organization_user_service.SORTABLE,
    )
    return await organization_user_service.list_users(session, organization_id, query)


@router.post("", response_model=OrganizationUser, status_code=status.HTTP_201_CREATED)
async def create_user(
    organization_id: uuid.UUID,
    body: OrganizationUserCreate,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.create_user(session, admin, organization_id, body)


@router.get("/{user_id}", response_model=OrganizationUser)
async def get_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    session: PlatformSessionDependency,
    _: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.get_user(session, organization_id, user_id)


@router.patch("/{user_id}", response_model=OrganizationUser)
async def update_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OrganizationUserUpdate,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.update_user(
        session, admin, organization_id, user_id, body
    )


@router.post("/{user_id}/disable", response_model=OrganizationUser)
async def disable_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.set_disabled(
        session, admin, organization_id, user_id, True
    )


@router.post("/{user_id}/enable", response_model=OrganizationUser)
async def enable_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.set_disabled(
        session, admin, organization_id, user_id, False
    )


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    body: PasswordReset,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Response:
    await organization_user_service.reset_password(
        session, admin, organization_id, user_id, body.new_password
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
