"""`/admin/organizations/{organizationId}/memberships`: an existing account joins an
organization, super admin only."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.auth import PlatformAdminDependency, PlatformSessionDependency
from app.models.api.organization_user import MembershipCreate, OrganizationUser
from app.services import organization_user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/organizations/{organization_id}/memberships", tags=["Platform"])


@router.post("", response_model=OrganizationUser, status_code=status.HTTP_201_CREATED)
async def add_membership(
    organization_id: uuid.UUID,
    body: MembershipCreate,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> OrganizationUser:
    return await organization_user_service.add_membership(session, admin, organization_id, body)
