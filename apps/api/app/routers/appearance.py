"""Appearance: domain colours, accent and source colour - read, change and reset."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.auth import CallerDependency, SessionDependency
from app.models.api.settings import Appearance, AppearancePatch
from app.services import appearance_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])


@router.get("/appearance", response_model=Appearance)
async def get_appearance(session: SessionDependency, caller: CallerDependency) -> Appearance:
    return await appearance_service.get_appearance(session, caller)


@router.patch("/appearance", response_model=Appearance)
async def update_appearance(
    body: AppearancePatch, session: SessionDependency, caller: CallerDependency
) -> Appearance:
    return await appearance_service.update_appearance(session, caller, body)


@router.post("/appearance/reset", response_model=Appearance)
async def reset_appearance(session: SessionDependency, caller: CallerDependency) -> Appearance:
    return await appearance_service.reset_appearance(session, caller)
