"""Ontology import: map a file to a stored draft tree, read it back, and propose it.

The proposing role, the `importDocs` setting and the import budget are checked before the
upload is read. The body is then read as it streams in, declared length or not, and refused
with `413` as soon as it passes the configured file limit plus the multipart framing.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, status
from starlette.datastructures import UploadFile

from app.auth import CallerDependency, SessionDependency
from app.config import get_settings
from app.models.api.ontology_import import OntologyImportResult, OntologyImportSubmission
from app.models.api.proposal import Proposal
from app.routers.imports import MULTIPART_OVERHEAD_BYTES, read_capped, replay
from app.services import ontology_import_service
from app.utilities.problems import ProblemError, validation_failed

logger = logging.getLogger(__name__)

router = APIRouter()

FORM_FIELDS = ("companyId", "parentConceptId", "languages", "individuals", "domainKey")


@router.post("/ontology-imports", response_model=OntologyImportResult, tags=["Teach"])
async def import_ontology(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> OntologyImportResult:
    await ontology_import_service.admit_import(session, caller)
    limit = get_settings().ontology_import_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + MULTIPART_OVERHEAD_BYTES:
        raise _too_large(limit)
    body = await read_capped(request, limit + MULTIPART_OVERHEAD_BYTES, _too_large(limit))
    form = await Request(request.scope, receive=replay(body)).form(
        max_files=1, max_fields=len(FORM_FIELDS) + 1
    )
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise validation_failed("file", "a file is required in the form field `file`")
        fields = {name: form.get(name) for name in FORM_FIELDS}
        for name, value in fields.items():
            if value is not None and not isinstance(value, str):
                raise validation_failed(name, f"{name} is a text field")
        data = await upload.read(limit + 1)
        return await ontology_import_service.import_ontology(
            session,
            caller,
            raw_file_name=upload.filename or "",
            content_type=upload.content_type,
            data=data,
            company_id=fields["companyId"],  # type: ignore[arg-type]
            parent_concept_id=fields["parentConceptId"],  # type: ignore[arg-type]
            languages=fields["languages"],  # type: ignore[arg-type]
            individuals=fields["individuals"],  # type: ignore[arg-type]
            domain_key=fields["domainKey"],  # type: ignore[arg-type]
        )
    finally:
        await form.close()


@router.get(
    "/ontology-imports/{ontology_import_id}", response_model=OntologyImportResult, tags=["Teach"]
)
async def get_ontology_import(
    ontology_import_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> OntologyImportResult:
    return await ontology_import_service.get_import(session, caller, ontology_import_id)


@router.post(
    "/ontology-imports/{ontology_import_id}/proposals",
    response_model=list[Proposal],
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Proposals"],
)
async def propose_ontology_import(
    ontology_import_id: uuid.UUID,
    body: OntologyImportSubmission,
    session: SessionDependency,
    caller: CallerDependency,
) -> list[Proposal]:
    return await ontology_import_service.propose(session, caller, ontology_import_id, body.indexes)


def _too_large(limit: int) -> ProblemError:
    return ProblemError(413, "payload_too_large", f"the file is larger than {limit} bytes")
