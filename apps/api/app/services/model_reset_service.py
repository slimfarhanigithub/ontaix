"""Model reset: one tenant-level change proposal that empties the model and keeps the companies.

Only an Administrator at tenant scope proposes it, which is the tenant's administrator or a super
admin who entered the organization. It is decided at tenant scope like any tenant-level proposal.
Approval rejects every other open proposal, removes every concept except the company roots with
every relation, and bumps the revision of each domain product it emptied. Companies, their roots,
domain products and sources, the tenant domains, users, groups, settings and the audit log stay.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import ChangeDraft
from app.models.api.proposal import Artefacts
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.base import ChangeKind, NodeKind, ProposalType
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import domain_product_repository, proposal_repository, relation_repository
from app.services import outbox_service
from app.services.concept_removal_service import remove_concepts
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import store
from app.services.rejection_service import OPEN_STATES, reject_one
from app.utilities.clock import get_clock
from app.utilities.layout import CONFLICT_COLOR
from app.utilities.permissions import can_manage
from app.utilities.problems import forbidden, validation_failed
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

TITLE = "Reset the model"
WHY = (
    "every other open proposal is rejected · the companies, their domain products and sources, "
    "the domains, users, groups, settings and the audit log stay"
)
CAPTION = "The model was reset. The companies stay, ready to be taught again."
ADMIN_ONLY_DETAIL = "Only a tenant administrator or a super admin can reset the model"
EMPTY_DETAIL = "the model is already empty"


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
    if enforce and not can_manage(caller.grants):
        raise forbidden(ADMIN_ONLY_DETAIL)
    concepts = _doomed(view)
    relations = len(view.live_relations())
    others = len(await proposal_repository.list_open(session, view.tenant_id))
    if not concepts and not relations and not others:
        raise validation_failed("changeKind", EMPTY_DETAIL)
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.RESET_MODEL,
        title=TITLE,
        color=CONFLICT_COLOR,
        company_id=None,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Remove <b>{_count(len(concepts), 'concept')}</b> and "
            f"{_count(relations, 'relation')} from every company, and reject "
            f"{_count(others, 'open proposal')}"
        ),
        why=WHY,
        caption=draft.caption or CAPTION,
        payload={},
        touched_company_ids=[],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def apply(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    bulk: bool,
) -> DecisionOutcome:
    outcome = DecisionOutcome(artefacts=Artefacts())
    for q in list(open_proposals):
        if q.id != proposal.id and q.state in OPEN_STATES:
            cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
            outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
            outcome.absorb_cascade(cascaded)
    doomed = _doomed(view)
    emptied = {c.domain_product_id for c in doomed if c.domain_product_id is not None}
    await remove_concepts(session, caller, view, proposal, doomed, outcome, bulk)
    await _remove_root_relations(session, caller, view, proposal, outcome, bulk)
    for product_id in emptied:
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


def _doomed(view: OntologyView) -> list[Concept]:
    """Every live concept except the company roots, approved or pending."""
    return [c for c in view.live_concepts() if c.kind is not NodeKind.ROOT]


async def _remove_root_relations(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    outcome: DecisionOutcome,
    bulk: bool,
) -> None:
    """The relations left once every other concept is gone join two company roots; each leaves
    with its own `relation.removed` event, so every company's canvas drops the line."""
    now = get_clock().now()
    for relation in view.live_relations():
        dto = view.relation_dto(relation)
        await relation_repository.mark_dying(session, relation, now)
        outcome.artefacts.relations.append(view.relation_dto(relation))
        await relation_repository.delete(session, relation)
        view.forget_relation(relation.id)
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "relation.removed",
            {"relationId": str(relation.id), "dying": True, "proposalId": str(proposal.id)},
            company_ids=dto.company_ids,
            bulk=bulk,
        )


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}" if n == 1 else f"{n:,} {noun}s"
