"""POST /teach/parse: one sentence to intents and proposal drafts."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.auth import CallerDependency, SessionDependency
from app.models.api.teach import TeachRequest, TeachResult
from app.services import teach_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teach"])


@router.post("/teach/parse", response_model=TeachResult)
async def parse_teach(
    body: TeachRequest, session: SessionDependency, caller: CallerDependency
) -> TeachResult:
    return await teach_service.parse(session, caller, body)
