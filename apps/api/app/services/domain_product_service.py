"""Domain products: reads and the immediate, audited visibility switch."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.domain_product import DomainProduct as DomainProductDto
from app.repositories import domain_product_repository
from app.services import audit_service, outbox_service
from app.services.company_service import readable_companies
from app.services.ontology_view_service import load_view
from app.utilities.permissions import can_read
from app.utilities.problems import forbidden, not_found

logger = logging.getLogger(__name__)


async def list_domain_products(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID | None
) -> list[DomainProductDto]:
    view = await load_view(session, caller.tenant_id)
    companies = readable_companies(caller, view)
    if company_id is not None:
        companies = [c for c in companies if c.id == company_id]
    return [
        view.domain_product_dto(p)
        for company in companies
        for p in view.company_domain_products(company.id)
    ]


async def get_domain_product(
    session: AsyncSession, caller: Caller, domain_product_id: uuid.UUID
) -> DomainProductDto:
    view = await load_view(session, caller.tenant_id)
    product = view.domain_products.get(domain_product_id)
    if product is None:
        raise not_found("domain product")
    if not can_read(caller.grants, product.company_id):
        raise forbidden("you may not read this company")
    return view.domain_product_dto(product)


async def set_hidden(
    session: AsyncSession, caller: Caller, domain_product_id: uuid.UUID, hidden: bool
) -> DomainProductDto:
    """Shared view state: any reader of the company may change it, and the change is audited."""
    view = await load_view(session, caller.tenant_id)
    product = view.domain_products.get(domain_product_id)
    if product is None:
        raise not_found("domain product")
    if not can_read(caller.grants, product.company_id):
        raise forbidden("you may not change the view of this company")
    await domain_product_repository.set_hidden(session, product, hidden)
    dto = view.domain_product_dto(product)
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        "list",
        f"{dto.name} {'hidden' if hidden else 'shown'}",
        True,
        company_ids=[product.company_id],
    )
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "domain_product.changed",
        {"domainProduct": dto.model_dump(mode="json", by_alias=True), "fields": ["hidden"]},
        company_ids=[product.company_id],
    )
    return dto
