"""Whole-document extraction jobs as the API serves them: start, status, cancel, result, submit.

A job belongs to the user who started it, in its tenant; anyone else is answered `404`. Every
operation needs `proposal.create` in the job company's scope through Owner or Builder. Starting
checks the import, the company and the channel, allows one job per import and one queued or
running job per user, spends one unit of the hourly `extraction` budget and queues the job; the
runner does the rest. The result is readable and submittable for 24 hours after the job
succeeded, and it is submitted by one successful call only.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.clients.db_client import get_session_factory
from app.config import get_settings
from app.models.api.document_extraction import (
    DocumentDraftNote,
    DocumentExtraction,
    DocumentExtractionResult,
    ExtractionSelection,
    ExtractionStart,
    ExtractionUnresolved,
    OutlineNode,
)
from app.models.api.proposal import Proposal as ProposalDto
from app.models.proposals.provenance import Provenance
from app.models.storage.base import ProposalOrigin
from app.models.storage.document_extraction_job import DocumentExtractionJob
from app.repositories import (
    document_extraction_job_repository,
    document_import_sentence_repository,
    tenant_settings_repository,
)
from app.services import import_service, stored_draft_service
from app.services.extraction_event_service import NODE, emit_changed, job_dto
from app.services.ontology_view_service import load_view
from app.services.rate_limit_service import Budget, charge, charge_proposals
from app.utilities.channels import ensure_import_allowed
from app.utilities.chunking import chunk_bounds
from app.utilities.clock import get_clock
from app.utilities.permissions import Scope, can_propose_as_builder, can_read
from app.utilities.problems import ProblemError, conflict, forbidden, not_found

logger = logging.getLogger(__name__)

# The stored note keeps the grounding sentence's `originDetail` next to the note the API shows.
ORIGIN_DETAIL = "originDetail"


async def start(
    session: AsyncSession, caller: Caller, import_id: uuid.UUID, body: ExtractionStart
) -> DocumentExtraction:
    row = await import_service.owned_import(session, caller, import_id)
    ensure_import_allowed(await tenant_settings_repository.get(session, caller.tenant_id))
    view = await load_view(session, caller.tenant_id)
    company = view.companies.get(body.company_id)
    if company is None or company.dying_at is not None or not can_read(caller.grants, company.id):
        raise not_found("company")
    _ensure_builder(caller, company.id)
    config = get_settings()
    if row.extracted_chars > config.document_extraction_max_chars:
        raise ProblemError(
            413,
            "payload_too_large",
            f"whole-document reading takes at most {config.document_extraction_max_chars}"
            " characters",
        )
    if await document_extraction_job_repository.exists_for_import(
        session, caller.tenant_id, row.id
    ):
        raise conflict("extraction_exists", "this document is being read or was read already")
    if await document_extraction_job_repository.has_active(
        session, caller.tenant_id, caller.user_id
    ):
        raise conflict("extraction_running", "another document of yours is being read")
    await charge(Budget.EXTRACTION, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    texts = await document_import_sentence_repository.texts_between(
        session, caller.tenant_id, row.id, 0, row.sentence_count
    )
    lengths = [len(texts[i]) for i in sorted(texts)]
    try:
        async with session.begin_nested():
            job = await document_extraction_job_repository.create(
                session,
                tenant_id=caller.tenant_id,
                actor_user_id=caller.user_id,
                import_id=row.id,
                company_id=company.id,
                chunks=len(chunk_bounds(lengths, config.document_extraction_chunk_chars)),
                token_ceiling=config.document_extraction_max_tokens,
                node_ceiling=config.document_extraction_max_nodes,
            )
    except IntegrityError as exc:
        raise conflict("extraction_running", "another document of yours is being read") from exc
    await emit_changed(session, job)
    return job_dto(job)


async def get(session: AsyncSession, caller: Caller, job_id: uuid.UUID) -> DocumentExtraction:
    return job_dto(await _owned(session, caller, job_id))


async def cancel(session: AsyncSession, caller: Caller, job_id: uuid.UUID) -> DocumentExtraction:
    job = await _owned(session, caller, job_id)
    if job.state in ("queued", "running"):
        if await document_extraction_job_repository.cancel_queued(
            session, caller.tenant_id, job.id
        ):
            job = await _reload(session, caller, job.id)
            await emit_changed(session, job)
        else:
            await document_extraction_job_repository.request_cancel(
                session, caller.tenant_id, job.id
            )
            job = await _reload(session, caller, job.id)
    return job_dto(job)


async def result(
    session: AsyncSession, caller: Caller, job_id: uuid.UUID
) -> DocumentExtractionResult:
    job = await _owned(session, caller, job_id)
    _ensure_readable_result(job)
    assert job.drafts is not None and job.notes is not None
    return DocumentExtractionResult(
        extraction_id=job.id,
        outline=[
            OutlineNode.model_validate(_outline_node(entry))
            for entry in job.outline
            if entry.get("kind") == NODE
        ],
        drafts=job.drafts,
        notes=[DocumentDraftNote.model_validate(_public_note(n)) for n in job.notes],
        unresolved=[ExtractionUnresolved.model_validate(u) for u in job.unresolved],
    )


async def propose(
    session: AsyncSession, caller: Caller, job_id: uuid.UUID, body: ExtractionSelection
) -> list[ProposalDto]:
    job = await _owned(session, caller, job_id)
    view = await load_view(session, caller.tenant_id)
    ensure_import_allowed(view.settings)
    if job.state != "succeeded":
        raise conflict("extraction_not_ready", "the document has not been read yet")
    if not await document_extraction_job_repository.claim_submit(session, caller.tenant_id, job.id):
        job = await _reload(session, caller, job.id)
        if job.submitted_at is not None:
            raise conflict("extraction_submitted", "this reading was proposed already")
        raise _expired()
    assert job.drafts is not None and job.notes is not None
    indexes = stored_draft_service.selected(body.indexes, job.notes)
    await charge_proposals(caller, len(indexes))
    drafts = [job.drafts[i] for i in indexes]
    provenances = [
        Provenance(ProposalOrigin.DOCUMENT, job.notes[i][ORIGIN_DETAIL]) for i in indexes
    ]
    return await stored_draft_service.propose(session, caller, view, drafts, provenances)


async def purge_expired() -> int:
    """Delete results more than 24 hours past their expiry and failed or cancelled jobs 48 hours
    after they ended, in their own transaction."""
    async with get_session_factory()() as session:
        deleted = await document_extraction_job_repository.delete_expired(
            session, get_clock().now()
        )
        await session.commit()
    return deleted


async def _owned(session: AsyncSession, caller: Caller, job_id: uuid.UUID) -> DocumentExtractionJob:
    job = await document_extraction_job_repository.get(session, caller.tenant_id, job_id)
    if job is None or job.actor_user_id != caller.user_id:
        raise not_found("extraction")
    if not can_read(caller.grants, job.company_id):
        raise not_found("extraction")
    _ensure_builder(caller, job.company_id)
    return job


async def _reload(
    session: AsyncSession, caller: Caller, job_id: uuid.UUID
) -> DocumentExtractionJob:
    job = await document_extraction_job_repository.get(session, caller.tenant_id, job_id)
    if job is None:
        raise not_found("extraction")
    return job


def _ensure_builder(caller: Caller, company_id: uuid.UUID) -> None:
    if not can_propose_as_builder(caller.grants, Scope(company_id=company_id)):
        raise forbidden("Whole-document reading needs the Owner or Builder role in this company")


def _ensure_readable_result(job: DocumentExtractionJob) -> None:
    if job.state != "succeeded":
        raise conflict("extraction_not_ready", "the document has not been read yet")
    if job.expires_at is not None and job.expires_at <= get_clock().now():
        raise _expired()


def _expired() -> ProblemError:
    return ProblemError(410, "extraction_expired", "the reading has expired; read it again")


def _outline_node(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": entry["index"],
        "parentIndex": entry.get("parentIndex"),
        "parentConceptId": entry.get("parentConceptId"),
        "conceptId": entry.get("conceptId"),
        "label": entry["label"],
        "role": entry["role"],
        "depth": entry["depth"],
        "sentenceIndex": entry["sentenceIndex"],
    }


def _public_note(note: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in note.items() if k != ORIGIN_DETAIL}
