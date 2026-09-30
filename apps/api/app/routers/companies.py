"""Companies: list, read, immediate creation, the removal proposal, and usage learning."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, Response, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.company import Company, CompanyCreate, CompanyCreated
from app.models.api.learning import (
    CompanyLearning,
    LearningReset,
    LearningResetResult,
    LearningSwitch,
    LearningSwitched,
)
from app.models.api.proposal import Proposal
from app.services import company_service, learning_service
from app.utilities.listing import parse_list_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Companies"])


@router.get("/companies", response_model=list[Company])
async def list_companies(session: SessionDependency, caller: CallerDependency) -> list[Company]:
    return await company_service.list_companies(session, caller)


@router.post("/companies", response_model=CompanyCreated, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate, session: SessionDependency, caller: CallerDependency
) -> CompanyCreated:
    return await company_service.create_company(session, caller, body)


@router.get("/companies/{company_id}", response_model=Company)
async def get_company(
    company_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Company:
    return await company_service.get_company(session, caller, company_id)


@router.delete(
    "/companies/{company_id}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_remove_company(
    company_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await company_service.propose_remove_company(session, caller, company_id)


@router.get("/companies/{company_id}/learning", response_model=CompanyLearning)
async def list_company_learning(
    company_id: uuid.UUID, request: Request, session: SessionDependency, caller: CallerDependency
) -> CompanyLearning:
    query = parse_list_query(
        request.query_params, learning_service.FILTERABLE, learning_service.SORTABLE
    )
    return await learning_service.list_learning(session, caller, company_id, query)


@router.patch("/companies/{company_id}/learning", response_model=LearningSwitched)
async def set_company_learning(
    company_id: uuid.UUID,
    body: LearningSwitch,
    session: SessionDependency,
    caller: CallerDependency,
) -> LearningSwitched:
    return await learning_service.set_switch(session, caller, company_id, body.enabled)


@router.post("/companies/{company_id}/learning/reset", response_model=LearningResetResult)
async def reset_company_learning(
    company_id: uuid.UUID,
    body: LearningReset,
    session: SessionDependency,
    caller: CallerDependency,
) -> LearningResetResult:
    return await learning_service.reset(session, caller, company_id, body)


@router.delete(
    "/companies/{company_id}/learning/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_company_lesson(
    company_id: uuid.UUID,
    lesson_id: uuid.UUID,
    session: SessionDependency,
    caller: CallerDependency,
) -> Response:
    await learning_service.delete_lesson(session, caller, company_id, lesson_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
