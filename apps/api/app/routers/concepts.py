"""Concepts: the Entities list, single reads, lineage, attributes and the proposal endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.attribute import Attribute
from app.models.api.concept import Concept, ConceptRename
from app.models.api.drafts import ConceptOrSpecDraft
from app.models.api.lineage import Lineage
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal
from app.services import concept_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Concepts"])


@router.get("/concepts", response_model=PageOf[Concept])
async def list_concepts(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> PageOf[Concept]:
    query = parse_list_query(
        request.query_params, concept_service.FILTERABLE, concept_service.SORTABLE
    )
    return await concept_service.list_concepts(session, caller, query)


@router.post("/concepts", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
async def propose_concept(
    draft: ConceptOrSpecDraft, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await concept_service.propose_concept(session, caller, draft)


@router.get("/concepts/{concept_id}", response_model=Concept)
async def get_concept(
    concept_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Concept:
    return await concept_service.get_concept(session, caller, concept_id)


@router.patch(
    "/concepts/{concept_id}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_rename_concept(
    concept_id: uuid.UUID,
    body: ConceptRename,
    session: SessionDependency,
    caller: CallerDependency,
) -> Proposal:
    return await concept_service.propose_rename(session, caller, concept_id, body.label)


@router.delete(
    "/concepts/{concept_id}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_delete_concept(
    concept_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await concept_service.propose_delete(session, caller, concept_id)


@router.get("/concepts/{concept_id}/lineage", response_model=Lineage)
async def get_concept_lineage(
    concept_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Lineage:
    return await concept_service.get_lineage(session, caller, concept_id)


@router.get("/concepts/{concept_id}/attributes", response_model=list[Attribute])
async def list_concept_attributes(
    concept_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> list[Attribute]:
    return await concept_service.list_attributes(session, caller, concept_id)
