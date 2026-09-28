"""Companies: list, read, immediate creation and the removal proposal."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.company import Company, CompanyCreate, CompanyCreated
from app.models.api.proposal import Proposal
from app.services import company_service

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
