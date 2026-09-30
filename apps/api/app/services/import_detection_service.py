"""Detects whether an upload is a document or an ontology, for the Studio's import routing.

The caller must be allowed to import (a proposing role, `importDocs` on); no import unit is
spent, as nothing is extracted or stored. An Office archive's header row is read in a child
process with a time limit and a memory cap, like every other untrusted-file parse; any other
file is judged in the request by its first 64 KiB only, so the work there is bounded.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.config import get_settings
from app.models.api.import_detection import ImportDetection
from app.repositories import tenant_settings_repository
from app.services import child_process_service
from app.utilities.channels import ensure_import_allowed
from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)
from app.utilities.document_text import (
    MAX_UPLOAD_BYTES,
    ZIP_SIGNATURE,
    base_name,
    file_name_problem,
)
from app.utilities.import_detection import DetectedImport, detect_import
from app.utilities.permissions import can_propose_anywhere
from app.utilities.problems import ProblemError, forbidden, validation_failed

logger = logging.getLogger(__name__)


def max_detect_bytes() -> int:
    """The largest file either import reads."""
    return max(MAX_UPLOAD_BYTES, get_settings().ontology_import_max_bytes)


async def admit_detection(session: AsyncSession, caller: Caller) -> None:
    """The checks that run before the upload is read: a proposing role and `importDocs`."""
    if not can_propose_anywhere(caller.grants, caller.everyone_teaches):
        raise forbidden("Your roles do not allow proposing")
    ensure_import_allowed(await tenant_settings_repository.get(session, caller.tenant_id))


async def detect(raw_file_name: str, content_type: str | None, data: bytes) -> ImportDetection:
    """The kind, ontology format and document media type of one admitted upload."""
    file_name = base_name(raw_file_name)
    problem = file_name_problem(file_name)
    if problem:
        raise validation_failed("file", problem)
    if len(data) > max_detect_bytes():
        raise ProblemError(413, "payload_too_large", "the file is larger than either import reads")
    try:
        if data.startswith(ZIP_SIGNATURE):
            detected: DetectedImport = await child_process_service.run(
                detect_import,
                (file_name, content_type, data),
                get_settings().ontology_import_parse_timeout_seconds,
                "the file",
            )
        else:
            detected = detect_import(file_name, content_type, data)
    except UnsupportedDocumentError as exc:
        raise ProblemError(415, "unsupported_media_type", str(exc)) from exc
    except DocumentTooLargeError as exc:
        raise ProblemError(413, "payload_too_large", str(exc)) from exc
    except DocumentUnreadableError as exc:
        raise validation_failed("file", str(exc)) from exc
    logger.info("import detection: %s %s %s", detected.kind, detected.format, detected.media_type)
    return ImportDetection(
        kind=detected.kind, format=detected.format, media_type=detected.media_type
    )
