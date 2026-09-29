"""POST /import/sentences: a document extracted server-side into stored sentences.

The permission, the `importDocs` setting and the import budget are checked before the upload
is read. The body is then read as it streams in, declared length or not, and refused with `413`
as soon as it passes the upload limit plus the multipart framing, so no more than that is ever
held in memory or spooled to disk.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile

from app.auth import CallerDependency, SessionDependency
from app.models.api.imports import ImportResult
from app.services import import_service
from app.utilities.document_text import MAX_UPLOAD_BYTES
from app.utilities.problems import ProblemError, validation_failed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teach"])

MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES


@router.post("/import/sentences", response_model=ImportResult)
async def import_sentences(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> ImportResult:
    await import_service.admit_import(session, caller)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise _too_large()
    body = await _read_capped(request)
    form = await Request(request.scope, receive=_replay(body)).form(max_files=1, max_fields=4)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise validation_failed("file", "a file is required in the form field `file`")
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        return await import_service.import_sentences(
            session, caller, upload.filename or "", upload.content_type, data
        )
    finally:
        await form.close()


async def _read_capped(request: Request) -> bytes:
    """The whole request body, refused with `413` the moment it passes `MAX_BODY_BYTES`."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _replay(body: bytes) -> Callable[[], Awaitable[dict[str, Any]]]:
    """An ASGI receive callable that hands the already read body to the form parser."""
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _too_large() -> ProblemError:
    return ProblemError(413, "payload_too_large", "the file is larger than 10 MiB")
