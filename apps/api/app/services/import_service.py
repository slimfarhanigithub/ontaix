"""Document imports: extract an upload into stored sentences, and give access to them.

An import belongs to the actor that created it, in its tenant; anyone else is answered `404`.
It serves teach parses and drafts for one hour, answers `410 import_expired` after that, and is
deleted by `purge_expired` once it is more than 24 hours past its expiry.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.imports import ImportResult
from app.models.api.origin import DocumentPosition, ImportOriginDetail
from app.models.storage.document_import import DocumentImport
from app.repositories import (
    document_import_repository,
    document_import_sentence_repository,
    tenant_settings_repository,
)
from app.repositories.document_import_sentence_repository import SentenceRow
from app.services import extraction_service, ocr_service
from app.services.rate_limit_service import Budget, charge
from app.utilities.channels import ensure_import_allowed
from app.utilities.clock import get_clock
from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)
from app.utilities.document_text import (
    MAX_UPLOAD_BYTES,
    agreed_media_type,
    base_name,
    file_name_problem,
    media_type_of,
    sentences_of_document,
    with_recognised_pages,
)
from app.utilities.permissions import can_propose_anywhere
from app.utilities.problems import ProblemError, conflict, forbidden, not_found, validation_failed

logger = logging.getLogger(__name__)

PURGE_AFTER_EXPIRY = timedelta(hours=24)
SUPPORTED_TYPES = (
    "text, Markdown, CSV, JSON, HTML, Word, PowerPoint, Excel and PDF documents are supported"
)


async def admit_import(session: AsyncSession, caller: Caller) -> None:
    """The checks that run before the upload is read: permission, setting, one import unit."""
    if not can_propose_anywhere(caller.grants, caller.everyone_teaches):
        raise forbidden("Your roles do not allow proposing")
    ensure_import_allowed(await tenant_settings_repository.get(session, caller.tenant_id))
    await charge(Budget.IMPORT, caller.tenant_id, caller.actor_kind.value, caller.user_id)


async def import_sentences(
    session: AsyncSession, caller: Caller, raw_file_name: str, content_type: str | None, data: bytes
) -> ImportResult:
    """Sniff, extract, recognise, charge and store one upload admitted by `admit_import`;
    nothing is stored when any step refuses. The type comes from the bytes and must agree with
    the declared one. Extraction runs in a child process with a time limit; image-only PDF pages
    are recognised by OCR. One parse unit per extracted sentence is spent before anything is
    stored.
    """
    file_name = base_name(raw_file_name)
    problem = file_name_problem(file_name)
    if problem:
        raise validation_failed("file", problem)
    declared = media_type_of(file_name, content_type)
    if declared is None:
        raise ProblemError(415, "unsupported_media_type", SUPPORTED_TYPES)
    if len(data) > MAX_UPLOAD_BYTES:
        raise _too_large("the file is larger than 10 MiB")
    try:
        media_type = agreed_media_type(declared, data)
        document = await extraction_service.extract(data, media_type)
    except UnsupportedDocumentError as exc:
        raise ProblemError(415, "unsupported_media_type", str(exc)) from exc
    except DocumentTooLargeError as exc:
        raise _too_large(str(exc)) from exc
    except DocumentUnreadableError as exc:
        raise validation_failed("file", str(exc)) from exc
    ocr_pages = len(document.image_pages)
    if document.image_pages:
        settings = await tenant_settings_repository.get(session, caller.tenant_id)
        recognised = await ocr_service.recognise(caller, settings, data, document.image_pages)
        try:
            document = with_recognised_pages(document, recognised)
        except DocumentTooLargeError as exc:
            raise _too_large(str(exc)) from exc
    try:
        sentences, extracted = sentences_of_document(document)
    except DocumentTooLargeError as exc:
        raise _too_large(str(exc)) from exc
    await charge(
        Budget.PARSE, caller.tenant_id, caller.actor_kind.value, caller.user_id, len(sentences)
    )
    row = await document_import_repository.create(
        session,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        file_name=file_name,
        media_type=media_type,
        sha256=hashlib.sha256(data).digest(),
        sentence_count=len(sentences),
        extracted_chars=extracted,
        ocr_pages=ocr_pages,
    )
    await document_import_sentence_repository.create_many(
        session,
        caller.tenant_id,
        row.id,
        [(s.text, s.unit, s.index, s.row if s.unit == "sheet" else None) for s in sentences],
    )
    logger.info("import %s: %d sentences of %s", row.id, len(sentences), media_type)
    return ImportResult(
        import_id=row.id,
        expires_at=row.expires_at,
        file_name=file_name,
        sentences=[s.text for s in sentences],
        origin="document",
        origin_detail=ImportOriginDetail(file_name=file_name, media_type=media_type),
        positions=[_position(s.unit, s.index, s.row) for s in sentences],
    )


async def owned_import(
    session: AsyncSession, caller: Caller, import_id: uuid.UUID
) -> DocumentImport:
    """The caller's own import in its tenant: `404` otherwise, `410` past its expiry."""
    row = await document_import_repository.get(session, caller.tenant_id, import_id)
    if row is None or row.actor_user_id != caller.user_id:
        raise not_found("import")
    if row.expires_at <= get_clock().now():
        raise ProblemError(410, "import_expired", "the import has expired; import the file again")
    return row


async def claim_parse(
    session: AsyncSession, caller: Caller, row: DocumentImport, sentence_index: int
) -> SentenceRow:
    """Count one teach parse of a stored sentence, at most three per sentence."""
    claimed = await document_import_sentence_repository.claim_parse(
        session, caller.tenant_id, row.id, sentence_index
    )
    if claimed is None:
        raise await _claim_refusal(session, caller, row, sentence_index, "parsed three times")
    return claimed


async def neighbours(
    session: AsyncSession, row: DocumentImport, sentence_index: int, count: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Up to `count` stored sentences just before and just after a stored sentence, in order."""
    texts = await document_import_sentence_repository.texts_between(
        session, row.tenant_id, row.id, sentence_index - count, sentence_index + count
    )
    before = tuple(texts[i] for i in range(sentence_index - count, sentence_index) if i in texts)
    after = tuple(
        texts[i] for i in range(sentence_index + 1, sentence_index + count + 1) if i in texts
    )
    return before, after


async def claim_draft(
    session: AsyncSession, caller: Caller, row: DocumentImport, sentence_index: int
) -> SentenceRow:
    """Mark a stored sentence drafted; one successful proposal call per sentence."""
    claimed = await document_import_sentence_repository.claim_draft(
        session, caller.tenant_id, row.id, sentence_index
    )
    if claimed is None:
        raise await _claim_refusal(session, caller, row, sentence_index, "drafted already")
    return claimed


def origin_detail(
    row: DocumentImport, sentence_index: int, sentence: SentenceRow
) -> dict[str, Any]:
    """The `originDetail` a proposal or a teach result citing this sentence carries."""
    detail: dict[str, Any] = {
        "fileName": row.file_name,
        "mediaType": row.media_type,
        "sentenceIndex": sentence_index,
    }
    position = _position(sentence.position_unit, sentence.position_index, sentence.position_row)
    if position is not None:
        detail["position"] = position.model_dump(mode="json", by_alias=True)
    return detail


async def purge_expired(session: AsyncSession) -> int:
    """Delete every import more than 24 hours past its expiry; returns how many went."""
    cutoff = get_clock().now() - PURGE_AFTER_EXPIRY
    return await document_import_repository.delete_expired_before(session, cutoff)


async def _claim_refusal(
    session: AsyncSession, caller: Caller, row: DocumentImport, sentence_index: int, what: str
) -> ProblemError:
    if not await document_import_sentence_repository.exists(
        session, caller.tenant_id, row.id, sentence_index
    ):
        return not_found("import sentence")
    return conflict("import_sentence_used", f"sentence {sentence_index} was {what}")


def _position(unit: str | None, index: int | None, row: int | None) -> DocumentPosition | None:
    """Where a sentence was found; a row is kept for a sheet only."""
    if not unit or not index:
        return None
    return DocumentPosition(unit=unit, index=index, row=row if unit == "sheet" else None)


def _too_large(detail: str) -> ProblemError:
    return ProblemError(413, "payload_too_large", detail)
