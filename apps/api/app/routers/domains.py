"""Tenant domains: the list, and the proposals that create or edit one."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.drafts import DOMAIN_KEY_PATTERN
from app.models.api.proposal import Proposal
from app.models.api.tenant_domain import DomainInput, DomainPatch, TenantDomain
from app.services import domain_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Companies"])

DomainKeyPath = Annotated[str, Path(pattern=DOMAIN_KEY_PATTERN)]


@router.get("/domains", response_model=list[TenantDomain])
async def list_domains(session: SessionDependency, caller: CallerDependency) -> list[TenantDomain]:
    return await domain_service.list_domains(session, caller)


@router.post("/domains", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
async def propose_create_domain(
    body: DomainInput, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await domain_service.propose_create(session, caller, body)


@router.patch(
    "/domains/{domain_key}", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED
)
async def propose_edit_domain(
    domain_key: DomainKeyPath,
    body: DomainPatch,
    session: SessionDependency,
    caller: CallerDependency,
) -> Proposal:
    return await domain_service.propose_edit(session, caller, domain_key, body)
