"""Whole-document extraction jobs: start one on a stored import, follow it, cancel it, read its
result and propose it."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.document_extraction import (
    DocumentExtraction,
    DocumentExtractionResult,
    ExtractionSelection,
    ExtractionStart,
)
from app.models.api.proposal import Proposal
from app.services import document_extraction_runner_service, document_extraction_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teach"])


@router.post(
    "/import/{import_id}/extraction",
    response_model=DocumentExtraction,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_document_extraction(
    import_id: uuid.UUID,
    body: ExtractionStart,
    background: BackgroundTasks,
    session: SessionDependency,
    caller: CallerDependency,
) -> DocumentExtraction:
    job = await document_extraction_service.start(session, caller, import_id, body)
    # Runs after the response, so after the request's transaction has committed the job.
    background.add_task(document_extraction_runner_service.wake)
    return job


@router.get("/extractions/{extraction_id}", response_model=DocumentExtraction)
async def get_document_extraction(
    extraction_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> DocumentExtraction:
    return await document_extraction_service.get(session, caller, extraction_id)


@router.delete(
    "/extractions/{extraction_id}",
    response_model=DocumentExtraction,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_document_extraction(
    extraction_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> DocumentExtraction:
    return await document_extraction_service.cancel(session, caller, extraction_id)


@router.get("/extractions/{extraction_id}/result", response_model=DocumentExtractionResult)
async def get_document_extraction_result(
    extraction_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> DocumentExtractionResult:
    return await document_extraction_service.result(session, caller, extraction_id)


@router.post(
    "/extractions/{extraction_id}/proposals",
    response_model=list[Proposal],
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Proposals"],
)
async def propose_document_extraction(
    extraction_id: uuid.UUID,
    body: ExtractionSelection,
    session: SessionDependency,
    caller: CallerDependency,
) -> list[Proposal]:
    return await document_extraction_service.propose(session, caller, extraction_id, body)
