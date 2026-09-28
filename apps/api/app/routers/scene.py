"""GET /scene: the one-call canvas snapshot."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.auth import CallerDependency, SessionDependency
from app.models.api.scene import Scene
from app.services import scene_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Scene"])


@router.get("/scene", response_model=Scene, response_model_by_alias=True)
async def get_scene(session: SessionDependency, caller: CallerDependency) -> Scene:
    return await scene_service.get_scene(session, caller)
