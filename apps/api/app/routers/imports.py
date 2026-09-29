"""POST /import/sentences: a document extracted server-side into stored sentences.

The permission, the `importDocs` setting and the import budget are checked before the upload
is read; a declared body larger than the upload limit is refused before it is parsed.
"""

from __future__ import annotations

import logging

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


@router.post("/import/sentences", response_model=ImportResult)
async def import_sentences(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> ImportResult:
    await import_service.admit_import(session, caller)
    declared = request.headers.get("content-length")
    if (
        declared
        and declared.isdigit()
        and int(declared) > MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES
    ):
        raise ProblemError(413, "payload_too_large", "the file is larger than 10 MiB")
    form = await request.form(max_files=1, max_fields=4)
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise validation_failed("file", "a file is required in the form field `file`")
    try:
        return await import_service.import_sentences(session, caller, upload)
    finally:
        await form.close()
