"""A company's domain product for a tenant domain key, created when its first concept joins.

Every company holds a domain product for each domain that existed when the company was added;
a domain created later gets its product in a company the first time a concept of that company
joins it, through a proposal, a move, a teach draft, a document extraction or an import.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.domain_product import DomainProduct
from app.repositories import domain_product_repository
from app.services.ontology_view_service import OntologyView
from app.utilities.problems import validation_failed

logger = logging.getLogger(__name__)


async def domain_product_for(
    session: AsyncSession, view: OntologyView, company_id: uuid.UUID, domain_key: str
) -> DomainProduct:
    """The company's domain product for `domain_key`, written now when the company has none;
    `422` when the key is not a domain of the tenant."""
    if domain_key not in view.domains:
        raise validation_failed("domainKey", f"unknown domain key {domain_key!r}")
    product = view.domain_product_by_key(company_id, domain_key)
    if product is None:
        product = await domain_product_repository.create(
            session, view.tenant_id, company_id, domain_key
        )
        view.register_domain_product(product)
    return product
