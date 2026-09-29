"""POST /speech/token: a short-lived Azure AI Speech token for the teach bar microphone."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

from app.auth import CallerDependency, SessionDependency
from app.models.api.speech import SpeechToken, SpeechTokenRequest
from app.services import speech_token_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teach"])


@router.post("/speech/token", response_model=SpeechToken)
async def mint_speech_token(
    body: SpeechTokenRequest,
    response: Response,
    session: SessionDependency,
    caller: CallerDependency,
) -> SpeechToken:
    response.headers["Cache-Control"] = "no-store"
    return await speech_token_service.mint(session, caller, body)
