"""Domain products: list, read and the visibility switch."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.auth import CallerDependency, SessionDependency
from app.models.api.domain_product import DomainProduct, DomainProductPatch
from app.models.api.proposal import Proposal
from app.services import domain_product_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Companies"])


@router.get("/domain-products", response_model=list[DomainProduct])
async def list_domain_products(
    session: SessionDependency,
    caller: CallerDependency,
    companyId: uuid.UUID | None = None,  # noqa: N803 - contract query parameter name
) -> list[DomainProduct]:
    return await domain_product_service.list_domain_products(session, caller, companyId)


@router.get("/domain-products/{domain_product_id}", response_model=DomainProduct)
async def get_domain_product(
    domain_product_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> DomainProduct:
    return await domain_product_service.get_domain_product(session, caller, domain_product_id)


@router.patch("/domain-products/{domain_product_id}", response_model=DomainProduct)
async def update_domain_product(
    domain_product_id: uuid.UUID,
    body: DomainProductPatch,
    session: SessionDependency,
    caller: CallerDependency,
) -> DomainProduct:
    return await domain_product_service.set_hidden(session, caller, domain_product_id, body.hidden)


@router.delete(
    "/domain-products/{domain_product_id}",
    response_model=Proposal,
    status_code=status.HTTP_202_ACCEPTED,
)
async def propose_delete_domain(
    domain_product_id: uuid.UUID, session: SessionDependency, caller: CallerDependency
) -> Proposal:
    return await domain_product_service.propose_delete(session, caller, domain_product_id)
