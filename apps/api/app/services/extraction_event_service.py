"""The `DocumentExtraction` view of a job and its `extraction.changed` event.

The event carries counts and states only, never a label or document text. Its audience is the
job's company and one recipient: the user who started the job, taken from the job row.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.api.document_extraction import DocumentExtraction
from app.models.storage.document_extraction_job import DocumentExtractionJob
from app.services import outbox_service

logger = logging.getLogger(__name__)

EVENT = "extraction.changed"
NODE = "node"


def job_dto(job: DocumentExtractionJob) -> DocumentExtraction:
    return DocumentExtraction(
        id=job.id,
        import_id=job.import_id,
        company_id=job.company_id,
        state=job.state,
        phase=job.phase,
        chunks=job.chunks,
        outline_chunks_done=job.outline_chunks_done,
        section_chunks_done=job.section_chunks_done,
        outline_nodes=sum(1 for entry in job.outline if entry.get("kind") == NODE),
        tokens_used=job.tokens_used,
        token_ceiling=job.token_ceiling,
        node_ceiling=job.node_ceiling,
        draft_count=job.draft_count,
        degraded=job.degraded,
        failure_reason=job.failure_reason,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        expires_at=job.expires_at,
        submitted_at=job.submitted_at,
    )


async def emit_changed(session: AsyncSession, job: DocumentExtractionJob) -> None:
    """Write the job's `extraction.changed` row in the caller's transaction."""
    await outbox_service.emit(
        session,
        job.tenant_id,
        Actor(kind="user", id=job.actor_user_id, name=None),
        EVENT,
        {"extraction": job_dto(job).model_dump(mode="json", by_alias=True)},
        company_ids=[job.company_id],
        recipient_user_id=job.actor_user_id,
    )
