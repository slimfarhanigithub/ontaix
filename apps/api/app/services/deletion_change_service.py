"""Deletion change proposals: delete a company's domain product, delete several items at once.

Both name what goes from the deletion impact computation. `delete_domain` removes every concept
of one company's domain product with their descendants, whatever their domain, and every
relation touching them; the tenant domain and the domain product stay. `delete_bulk` removes up
to 200 concepts and 20 domain products of one company at once, all or nothing, each item with
the semantics of `delete_concept` or `delete_domain`. Approval rejects by cascade the open
proposals that touch what goes.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.deletion_impact import DeletionTarget
from app.models.api.drafts import ChangeDraft
from app.models.api.proposal import Artefacts
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.base import ChangeKind, ProposalType
from app.models.storage.concept import Concept
from app.models.storage.domain_product import DomainProduct
from app.models.storage.proposal import Proposal
from app.repositories import domain_product_repository, proposal_repository
from app.services import outbox_service
from app.services.concept_removal_service import remove_concepts
from app.services.deletion_impact_service import describe, names_line, resolve, to_impact
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import (
    ensure_can_propose,
    ensure_company_still_live,
    esc,
    store,
)
from app.services.rejection_service import OPEN_STATES, reject_one, touches_any
from app.utilities.layout import CONFLICT_COLOR
from app.utilities.permissions import Scope
from app.utilities.problems import conflict, not_found, validation_failed
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

DOMAIN_STAYS = "the domain stays available"
BULK_WHY = "all or nothing · descendants and relations go with them"
MAX_BULK_NAMES_IN_HTML = 3


async def propose(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    if draft.change_kind == "delete_domain":
        return await _propose_delete_domain(
            session, caller, proposer, view, draft, bulk, enforce, provenance
        )
    return await _propose_delete_bulk(
        session, caller, proposer, view, draft, bulk, enforce, provenance
    )


async def apply(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    if proposal.change_kind is ChangeKind.DELETE_DOMAIN:
        return await _apply_delete_domain(session, caller, view, proposal, open_proposals, bulk)
    return await _apply_delete_bulk(session, caller, view, proposal, open_proposals, bulk)


async def _propose_delete_domain(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance,
) -> Proposal:
    if draft.payload.domain_product_id is None:
        raise validation_failed("payload.domainProductId", "domainProductId is required")
    product = view.domain_products.get(draft.payload.domain_product_id)
    if product is None:
        raise not_found("domain product")
    company = view.companies.get(product.company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if enforce:
        ensure_can_propose(caller, Scope(company.id, product.template_key))
    await ensure_company_still_live(session, view, company)
    doomed = resolve(
        view,
        caller.grants,
        DeletionTarget(company_id=company.id, domain_product_ids=[product.id]),
        await proposal_repository.list_open(session, view.tenant_id),
    )
    impact = to_impact(doomed)
    domain = view.domains[product.template_key]
    names = names_line(impact)
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.DELETE_DOMAIN,
        title=f"Delete {domain.name}",
        color=CONFLICT_COLOR,
        company_id=company.id,
        domain_product_id=product.id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Delete <b>{esc(domain.name)}</b> with its {esc(describe(impact))}",
        why=f"{names} go with it · {DOMAIN_STAYS}" if names else DOMAIN_STAYS,
        caption=draft.caption or f"{domain.name} was emptied in {company.name}.",
        payload={"domainProductId": str(product.id)},
        touched_company_ids=[company.id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_delete_bulk(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance,
) -> Proposal:
    if draft.payload.company_id is None:
        raise validation_failed("payload.companyId", "companyId is required")
    concept_ids = draft.payload.concept_ids or []
    product_ids = draft.payload.domain_product_ids or []
    if not concept_ids and not product_ids:
        raise validation_failed("payload", "conceptIds or domainProductIds is required")
    target = DeletionTarget(
        company_id=draft.payload.company_id,
        concept_ids=concept_ids,
        domain_product_ids=product_ids,
    )
    doomed = resolve(
        view, caller.grants, target, await proposal_repository.list_open(session, view.tenant_id)
    )
    company = doomed.company
    if enforce:
        named_ids = set(concept_ids)
        for concept in doomed.named:
            if concept.id in named_ids:
                ensure_can_propose(caller, Scope(company.id, view.domain_key(concept)))
        for product in doomed.products:
            ensure_can_propose(caller, Scope(company.id, product.template_key))
    await ensure_company_still_live(session, view, company)
    impact = to_impact(doomed)
    shown = [esc(c.label) for c in doomed.named[:MAX_BULK_NAMES_IN_HTML]]
    rest = len(doomed.named) - len(shown)
    subject = ", ".join(f"<b>{s}</b>" for s in shown) + (f" and {rest} more" if rest > 0 else "")
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.DELETE_BULK,
        title=_bulk_title(len(concept_ids), len(product_ids)),
        color=CONFLICT_COLOR,
        company_id=company.id,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Delete {subject} with their {esc(describe(impact, concepts=False))}"
            if subject
            else f"Delete {esc(describe(impact))}"
        ),
        why=BULK_WHY,
        caption=draft.caption or f"{len(doomed.concepts)} concepts left {company.name}.",
        payload={
            "conceptIds": [str(i) for i in concept_ids],
            "domainProductIds": [str(i) for i in product_ids],
        },
        touched_company_ids=[company.id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _apply_delete_domain(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    product = view.domain_products.get(uuid.UUID(str(proposal.payload["domainProductId"])))
    if product is None:
        raise conflict("proposal_not_ready", "the domain product no longer exists")
    named = [c for c in view.live_concepts() if c.domain_product_id == product.id]
    doomed = _with_descendants(view, named)
    outcome = DecisionOutcome(artefacts=Artefacts())
    await _cascade(session, caller, view, proposal, open_proposals, doomed, outcome)
    await remove_concepts(session, caller, view, proposal, doomed, outcome, bulk)
    return outcome


async def _apply_delete_bulk(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    payload = proposal.payload
    named: list[Concept] = []
    products: list[DomainProduct] = []
    for concept_id in payload.get("conceptIds") or []:
        concept = view.concepts.get(uuid.UUID(str(concept_id)))
        if concept is None or concept.dying_at is not None:
            raise conflict("proposal_not_ready", "a concept of the selection no longer exists")
        named.append(concept)
    for product_id in payload.get("domainProductIds") or []:
        product = view.domain_products.get(uuid.UUID(str(product_id)))
        if product is None:
            raise conflict("proposal_not_ready", "a domain of the selection no longer exists")
        products.append(product)
        named.extend(c for c in view.live_concepts() if c.domain_product_id == product.id)
    touched_products = {c.domain_product_id for c in named if c.domain_product_id is not None} | {
        p.id for p in products
    }
    doomed = _with_descendants(view, list(dict.fromkeys(named)))
    outcome = DecisionOutcome(artefacts=Artefacts())
    await _cascade(session, caller, view, proposal, open_proposals, doomed, outcome)
    await remove_concepts(session, caller, view, proposal, doomed, outcome, bulk)
    for product_id in touched_products:
        product = view.domain_products.get(product_id)
        if product is None:
            continue
        await domain_product_repository.bump_revision(session, product)
        dto = view.domain_product_dto(product)
        outcome.artefacts.domain_products.append(dto)
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "domain_product.changed",
            {"domainProduct": dto.model_dump(mode="json", by_alias=True), "fields": ["revision"]},
            company_ids=[product.company_id],
            bulk=bulk,
        )
    return outcome


async def _cascade(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    doomed: list[Concept],
    outcome: DecisionOutcome,
) -> None:
    """Reject every other open proposal that touches a doomed concept."""
    for q in list(open_proposals):
        if q.id != proposal.id and q.state in OPEN_STATES and touches_any(view, q, doomed):
            cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
            outcome.absorb_cascade(cascaded)


def _with_descendants(view: OntologyView, named: list[Concept]) -> list[Concept]:
    out = list(named)
    seen = {c.id for c in named}
    for concept in named:
        for descendant in view.descendants_of(concept.id):
            if descendant.id not in seen:
                seen.add(descendant.id)
                out.append(descendant)
    return out


def _bulk_title(concepts: int, products: int) -> str:
    parts: list[str] = []
    if concepts:
        parts.append(f"{concepts} concept" if concepts == 1 else f"{concepts} concepts")
    if products:
        parts.append(f"{products} domain" if products == 1 else f"{products} domains")
    return "Delete " + " and ".join(parts)
