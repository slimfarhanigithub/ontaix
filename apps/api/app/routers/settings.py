"""Tenant settings: the read, the immediate change, and the companies-may-interact switch."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.auth import CallerDependency, SessionDependency
from app.models.api.settings import (
    CrossCompanyDisable,
    CrossCompanyDisabled,
    CrossCompanyImpact,
    Settings,
    SettingsPatch,
)
from app.services import settings_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])


@router.get("/settings", response_model=Settings)
async def get_settings(session: SessionDependency, caller: CallerDependency) -> Settings:
    return await settings_service.get_settings(session, caller)


@router.patch("/settings", response_model=Settings)
async def update_settings(
    body: SettingsPatch, session: SessionDependency, caller: CallerDependency
) -> Settings:
    return await settings_service.update_settings(session, caller, body)


@router.get("/settings/cross-company/impact", response_model=CrossCompanyImpact)
async def get_cross_company_impact(
    session: SessionDependency, caller: CallerDependency
) -> CrossCompanyImpact:
    return await settings_service.cross_company_impact(session, caller)


@router.post("/settings/cross-company/disable", response_model=CrossCompanyDisabled)
async def disable_cross_company(
    body: CrossCompanyDisable, session: SessionDependency, caller: CallerDependency
) -> CrossCompanyDisabled:
    return await settings_service.disable_cross_company(session, caller, body)
