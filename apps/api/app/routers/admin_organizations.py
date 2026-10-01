"""`/admin/organizations`: the super admin's organizations and their groups (for user dialogs)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, status

from app.auth import PlatformAdminDependency, PlatformSessionDependency
from app.models.api.group import Group
from app.models.api.organization import Organization, OrganizationCreate, OrganizationUpdate
from app.models.api.page import PageOf
from app.services import organization_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/organizations", tags=["Platform"])


@router.get("", response_model=PageOf[Organization])
async def list_organizations(
    request: Request, session: PlatformSessionDependency, _: PlatformAdminDependency
) -> PageOf[Organization]:
    query = parse_list_query(
        request.query_params, organization_service.FILTERABLE, organization_service.SORTABLE
    )
    return await organization_service.list_organizations(session, query)


@router.post("", response_model=Organization, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate, session: PlatformSessionDependency, admin: PlatformAdminDependency
) -> Organization:
    return await organization_service.create_organization(session, admin, body)


@router.get("/{organization_id}", response_model=Organization)
async def get_organization(
    organization_id: uuid.UUID, session: PlatformSessionDependency, _: PlatformAdminDependency
) -> Organization:
    return await organization_service.get_organization(session, organization_id)


@router.patch("/{organization_id}", response_model=Organization)
async def update_organization(
    organization_id: uuid.UUID,
    body: OrganizationUpdate,
    session: PlatformSessionDependency,
    admin: PlatformAdminDependency,
) -> Organization:
    return await organization_service.update_organization(session, admin, organization_id, body)


@router.post("/{organization_id}/disable", response_model=Organization)
async def disable_organization(
    organization_id: uuid.UUID, session: PlatformSessionDependency, admin: PlatformAdminDependency
) -> Organization:
    return await organization_service.set_disabled(session, admin, organization_id, True)


@router.post("/{organization_id}/enable", response_model=Organization)
async def enable_organization(
    organization_id: uuid.UUID, session: PlatformSessionDependency, admin: PlatformAdminDependency
) -> Organization:
    return await organization_service.set_disabled(session, admin, organization_id, False)


@router.get("/{organization_id}/groups", response_model=list[Group])
async def list_organization_groups(
    organization_id: uuid.UUID, session: PlatformSessionDependency, _: PlatformAdminDependency
) -> list[Group]:
    return await organization_service.list_groups(session, organization_id)
