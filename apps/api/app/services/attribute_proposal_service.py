"""Taught attribute proposals: a value a person stated about a concept, as a proposed attribute.

The concept is given by id, or by label when an earlier draft of the same batch introduces it;
a proposal on a pending concept waits for that concept's approval. Approval turns the attribute
approved and rejection deletes it, each with an `attribute.changed` event. An attribute read
from a bound source is proposed by the bindings module.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import AttributeDraft
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.attribute import Attribute
from app.models.storage.base import AttributeState, AttributeType, ProposalType
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import attribute_repository
from app.services import outbox_service
from app.services.ontology_view_service import OntologyView, attribute_dto
from app.services.proposal_store_service import ensure_can_propose, ensure_still_live, esc, store
from app.utilities.permissions import Scope
from app.utilities.problems import ProblemError, conflict, not_found

logger = logging.getLogger(__name__)


async def propose_attribute(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: AttributeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    if not draft.taught or draft.value is None:
        raise ProblemError(
            503, "unavailable", "attributes read from a source are served by the bindings module"
        )
    concept = _concept(view, draft)
    if enforce:
        ensure_can_propose(caller, Scope(concept.company_id, view.domain_key(concept)))
    name = draft.name.lower()
    if view.attribute_named(concept.id, name) is not None or await attribute_repository.name_taken(
        session, view.tenant_id, concept.id, name
    ):
        raise conflict("duplicate_attribute", f"{concept.label} already has {name}")
    await ensure_still_live(session, view, concept)
    attribute = await attribute_repository.create_taught(
        session,
        tenant_id=view.tenant_id,
        concept_id=concept.id,
        name=name,
        type=AttributeType(draft.attribute_type),
        value=draft.value,
    )
    view.register_attribute(attribute)
    proposal = await store(
        session,
        proposer,
        view,
        type=ProposalType.ATTR,
        change_kind=None,
        title=f"{concept.label}.{name}",
        color=view.concept_color(concept),
        company_id=concept.company_id,
        domain_product_id=concept.domain_product_id,
        parent_label=None,
        deps=[concept.label] if concept.pending else [],
        wait_for=concept.label if concept.pending else None,
        html=(
            f"<b>{esc(concept.label)}</b> has <b>{esc(name)}</b>"
            f" <i>· {esc(draft.attribute_type)} · {esc(draft.value)}</i>"
        ),
        why="taught · not yet in the model",
        caption=f"{concept.label} {name}: {draft.value} is now part of the model.",
        payload={},
        touched_company_ids=[concept.company_id],
        concept_id=None,
        relation_id=None,
        attribute_id=attribute.id,
        bulk=bulk,
        provenance=provenance,
    )
    await emit_changed(session, view, proposer, attribute, proposal, removed=False, bulk=bulk)
    return proposal


async def approve(
    session: AsyncSession, view: OntologyView, caller: Caller, proposal: Proposal, bulk: bool
) -> None:
    """The proposal's attribute becomes approved; a proposal whose attribute is gone is not
    ready."""
    attribute = view.attribute(proposal.attribute_id)
    if attribute is None:
        raise conflict("proposal_not_ready", "the attribute no longer exists")
    await attribute_repository.approve(session, attribute)
    await emit_changed(session, view, caller.actor, attribute, proposal, removed=False, bulk=bulk)


async def remove(
    session: AsyncSession, view: OntologyView, caller: Caller, proposal: Proposal, bulk: bool
) -> None:
    """The proposal's still proposed attribute leaves with the rejected proposal."""
    attribute = view.attribute(proposal.attribute_id)
    if attribute is None or attribute.state is not AttributeState.PROPOSED:
        return
    await emit_changed(session, view, caller.actor, attribute, proposal, removed=True, bulk=bulk)
    await attribute_repository.delete(session, attribute)
    view.forget_attribute(attribute)


async def emit_changed(
    session: AsyncSession,
    view: OntologyView,
    actor: Actor,
    attribute: Attribute,
    proposal: Proposal,
    *,
    removed: bool,
    bulk: bool,
) -> None:
    concept = view.concepts.get(attribute.concept_id)
    await outbox_service.emit(
        session,
        view.tenant_id,
        actor,
        "attribute.changed",
        {
            "conceptId": str(attribute.concept_id),
            "attribute": attribute_dto(attribute).model_dump(mode="json", by_alias=True),
            "removed": removed,
            "proposalId": str(proposal.id),
        },
        company_ids=[concept.company_id] if concept is not None else [],
        bulk=bulk,
    )


def _concept(view: OntologyView, draft: AttributeDraft) -> Concept:
    if draft.concept_id is not None:
        concept = view.concepts.get(draft.concept_id)
        if concept is None or concept.dying_at is not None:
            raise not_found("concept")
        return concept
    if draft.company_id is None or draft.company_id not in view.companies:
        raise not_found("company")
    concept = view.find_label(draft.company_id, draft.concept_label or "")
    if concept is None:
        raise not_found(f"concept {draft.concept_label!r}")
    return concept
