"""POST /teach/parse: one sentence to intents and proposal drafts, whole or streamed."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.auth import CallerDependency, SessionDependency
from app.models.api.teach import TeachRequest, TeachResult
from app.services import teach_service, teach_stream_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teach"])

# The stream is read as it arrives: never cached, and never held back by a buffering proxy.
STREAM_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


@router.post("/teach/parse", response_model=TeachResult)
async def parse_teach(
    body: TeachRequest, session: SessionDependency, caller: CallerDependency
) -> TeachResult:
    return await teach_service.parse(session, caller, body)


@router.post(
    "/teach/parse/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {teach_stream_service.MEDIA_TYPE: {}}}},
)
async def parse_teach_stream(
    body: TeachRequest, session: SessionDependency, caller: CallerDependency
) -> StreamingResponse:
    # The request's refusals are raised here, before the stream begins; the request session
    # commits when this function returns, and the stream uses none.
    prepared = await teach_service.prepare(session, caller, body)
    return StreamingResponse(
        teach_stream_service.events(prepared),
        media_type=teach_stream_service.MEDIA_TYPE,
        headers=STREAM_HEADERS,
    )
