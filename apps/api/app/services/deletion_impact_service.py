"""What a deletion would remove: the one computation behind `POST /deletion-impact` and the
texts of the company, domain and bulk deletion proposals.

A deletion targets a whole company, or concepts and domain products of one company. What goes
is the named concepts (each concept of a named domain product counts as named), their
descendants through the parent chain, every live relation touching any of them (counted once,
cross-company ones counted separately), their attributes, and the open proposals a cascade
would reject. Only what the caller may read is counted. Sources and bindings are served by the
bindings module and count zero until it exists.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.deletion_impact import MAX_IMPACT_NAMES, DeletionImpact, DeletionTarget
from app.models.storage.base import NodeKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.domain_product import DomainProduct
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.repositories import proposal_repository
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rejection_service import OPEN_STATES, touches_any
from app.utilities.permissions import Grant, can_read, can_read_proposal
from app.utilities.problems import conflict, not_found, validation_failed
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)


@dataclass
class Doomed:
    """The rows a deletion removes, resolved against the view."""

    company: Company
    whole_company: bool
    named: list[Concept]
    descendants: list[Concept]
    products: list[DomainProduct]
    relations: list[Relation]
    cross_company: list[Relation]
    attributes: int
    cascaded: list[Proposal] = field(default_factory=list)

    @property
    def concepts(self) -> list[Concept]:
        return [*self.named, *self.descendants]


async def impact_for(
    session: AsyncSession, caller: Caller, target: DeletionTarget
) -> DeletionImpact:
    """`POST /deletion-impact`: pure, computed from the current view."""
    open_proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id)
    return to_impact(resolve(view, caller.grants, target, open_proposals))


def resolve(
    view: OntologyView,
    grants: tuple[Grant, ...],
    target: DeletionTarget,
    open_proposals: list[Proposal],
) -> Doomed:
    """Resolve the target against the view: `404` for a company, concept or domain product the
    caller cannot read or that does not exist, `422` for items outside the company, `409
    root_concept` for the company root."""
    company = view.companies.get(target.company_id)
    if company is None or company.dying_at is not None or not can_read(grants, company.id):
        raise not_found("company")
    if target.whole_company:
        named = [
            c
            for c in view.live_concepts()
            if c.company_id == company.id and c.kind is NodeKind.CONCEPT
        ]
        anchors = [c for c in view.concepts.values() if c.company_id == company.id]
        descendants: list[Concept] = []
        products: list[DomainProduct] = []
    else:
        named, products = _named(view, company, target)
        descendants = _descendants(view, named)
        anchors = [*named, *descendants]
    anchor_ids = {c.id for c in anchors}
    relations, cross_company = _relations(view, grants, anchor_ids)
    attributes = sum(len(view.attributes.get(c.id, [])) for c in anchors)
    doomed = Doomed(
        company=company,
        whole_company=target.whole_company,
        named=named,
        descendants=descendants,
        products=products,
        relations=relations,
        cross_company=cross_company,
        attributes=attributes,
    )
    doomed.cascaded = [
        q
        for q in open_proposals
        if q.state in OPEN_STATES
        and can_read_proposal(grants, proposal_company_ids(q))
        and ((target.whole_company and q.company_id == company.id) or touches_any(view, q, anchors))
    ]
    return doomed


def to_impact(doomed: Doomed) -> DeletionImpact:
    names = [c.label for c in doomed.named] + [c.label for c in doomed.descendants]
    return DeletionImpact(
        concepts=len(doomed.named),
        descendants=len(doomed.descendants),
        relations=len(doomed.relations),
        cross_company_relations=len(doomed.cross_company),
        bindings=0,
        attributes=doomed.attributes,
        sources=0,
        cascaded_proposals=len(doomed.cascaded),
        names=names[:MAX_IMPACT_NAMES],
    )


def describe(impact: DeletionImpact, *, concepts: bool = True) -> str:
    """Counts as prose: `3 concepts, 2 descendants and 5 relations (1 across companies)`."""
    parts: list[str] = []
    if concepts:
        parts.append(_count(impact.concepts, "concept"))
    if impact.descendants:
        parts.append(_count(impact.descendants, "descendant"))
    relations = _count(impact.relations, "relation")
    if impact.cross_company_relations:
        relations += f" ({impact.cross_company_relations} across companies)"
    parts.append(relations)
    if impact.bindings:
        parts.append(_count(impact.bindings, "binding"))
    if impact.attributes:
        parts.append(_count(impact.attributes, "attribute"))
    if impact.sources:
        parts.append(_count(impact.sources, "source"))
    if impact.cascaded_proposals:
        parts.append(_count(impact.cascaded_proposals, "open proposal"))
    return _join(parts)


def names_line(impact: DeletionImpact) -> str | None:
    """`Pump, Valve and 4 more`, or None when nothing is named."""
    total = impact.concepts + impact.descendants
    if not impact.names:
        return None
    shown = list(impact.names)
    rest = total - len(shown)
    if rest > 0:
        return ", ".join(shown) + f" and {rest} more"
    return _join(shown)


def _named(
    view: OntologyView, company: Company, target: DeletionTarget
) -> tuple[list[Concept], list[DomainProduct]]:
    named: list[Concept] = []
    seen: set[uuid.UUID] = set()
    for concept_id in target.concept_ids or []:
        concept = view.concepts.get(concept_id)
        if concept is None or concept.dying_at is not None:
            raise not_found("concept")
        if concept.company_id != company.id:
            raise validation_failed("conceptIds", "every concept belongs to the one company")
        if concept.kind is NodeKind.ROOT:
            raise conflict("root_concept", "the company root cannot be deleted")
        if concept.id not in seen:
            seen.add(concept.id)
            named.append(concept)
    products: list[DomainProduct] = []
    for product_id in target.domain_product_ids or []:
        product = view.domain_products.get(product_id)
        if product is None:
            raise not_found("domain product")
        if product.company_id != company.id:
            raise validation_failed(
                "domainProductIds", "every domain product belongs to the one company"
            )
        products.append(product)
        for concept in view.live_concepts():
            if concept.domain_product_id == product.id and concept.id not in seen:
                seen.add(concept.id)
                named.append(concept)
    return named, products


def _descendants(view: OntologyView, named: list[Concept]) -> list[Concept]:
    seen = {c.id for c in named}
    out: list[Concept] = []
    for concept in named:
        for descendant in view.descendants_of(concept.id):
            if descendant.id not in seen:
                seen.add(descendant.id)
                out.append(descendant)
    return out


def _relations(
    view: OntologyView, grants: tuple[Grant, ...], anchor_ids: set[uuid.UUID]
) -> tuple[list[Relation], list[Relation]]:
    """Live relations touching any anchor, each once, when both ends are readable."""
    relations: list[Relation] = []
    cross_company: list[Relation] = []
    for relation in view.live_relations():
        if relation.a_id not in anchor_ids and relation.b_id not in anchor_ids:
            continue
        a, b = view.concepts.get(relation.a_id), view.concepts.get(relation.b_id)
        if a is None or b is None:
            continue
        if not (can_read(grants, a.company_id) and can_read(grants, b.company_id)):
            continue
        relations.append(relation)
        if a.company_id != b.company_id:
            cross_company.append(relation)
    return relations, cross_company


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"
