"""Relations and equivalences: lists, single reads and the proposal endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.drafts import RelationDraft
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal
from app.models.api.relation import EquivalenceDraft, Relation, RelationEdit
from app.services import relation_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Relations"])


@router.get("/relations", response_model=PageOf[Relation])
async def list_relations(
    request: Request, session: SessionDependency, caller: CallerDependency
) -> PageOf[Relation]:
    query = parse_list_query(
        request.query_params, relation_service.FILTERABLE, relation_service.SORTABLE
    )
    return await relation_service.list_relations(session, caller, query)


@router.post("/relations", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
async def propose_relation(
    draft: RelationDraft, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await relation_service.propose_relation(session, caller, draft)


@router.get("/relations/{relation_id}", response_model=Relation)
async def get_relation(
    relation_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Relation:
    return await relation_service.get_relation(session, caller, relation_id)


@router.patch(
    "/relations/{relation_id}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_edit_relation(
    relation_id: uuid.UUID,
    body: RelationEdit,
    session: SessionDependency,
    caller: CallerDependency,
) -> Proposal:
    return await relation_service.propose_edit(session, caller, relation_id, body)


@router.delete(
    "/relations/{relation_id}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_remove_relation(
    relation_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await relation_service.propose_remove(session, caller, relation_id)


@router.get("/equivalences", response_model=list[Relation])
async def list_equivalences(session: SessionDependency, caller: CallerDependency) -> list[Relation]:
    return await relation_service.list_equivalences(session, caller)


@router.post("/equivalences", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
async def propose_equivalence(
    body: EquivalenceDraft, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await relation_service.propose_equivalence(
        session, caller, body.a_id, body.b_id, body.caption
    )
