"""GET /export: the ontology as OWL 2, SKOS or a Word document, sent as an attachment.

The file is written before the response starts, then streamed in chunks, so a large export
never goes out as one body write. The response is never cached.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.auth import CallerDependency, SessionDependency
from app.services import export_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Export"])

CHUNK_BYTES = 64 * 1024


@router.get(
    "/export",
    response_class=StreamingResponse,
    responses={200: {"description": "The export file."}},
)
async def export_ontology(
    session: SessionDependency,
    caller: CallerDependency,
    scope: str | None = None,
    companyId: str | None = None,  # noqa: N803 - the contract's query parameter name
    domainProductId: str | None = None,  # noqa: N803 - the contract's query parameter name
    format: str | None = None,  # noqa: A002 - the contract's query parameter name
) -> StreamingResponse:
    exported = await export_service.export(
        session,
        caller,
        scope=scope,
        company_id=companyId,
        domain_product_id=domainProductId,
        fmt=format,
    )
    return StreamingResponse(
        _chunks(exported.content),
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.file_name}"',
            "Cache-Control": "no-store",
        },
    )


def _chunks(content: bytes) -> Iterator[bytes]:
    view = memoryview(content)
    for start in range(0, len(content), CHUNK_BYTES):
        yield bytes(view[start : start + CHUNK_BYTES])
