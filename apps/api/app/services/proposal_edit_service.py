"""Editing a pending draft in place: the label and action of a concept, spec or relation proposal.

The edit changes the proposal itself, which is still approved or rejected as a whole, so it
needs no approval of its own. It takes the tenant decision lock, so an edit and a decision never
interleave, and it is guarded by the proposal's revision: the body carries the revision the
editor saw, and the revision increments on success. Every creation check runs again, the
proposal's texts and pending artefacts are rebuilt, and the open proposals that named the old
label in their dependencies are rewritten.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import Proposal as ProposalDto
from app.models.api.proposal import ProposalEdit
from app.models.storage.base import ProposalState, ProposalType, RelationKind
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.repositories import concept_repository, proposal_repository, relation_repository
from app.services import audit_service, decision_lock_service, outbox_service
from app.services.concept_proposal_service import concept_panel_html, spec_panel_html
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_store_service import ISA_ACTION, SAME_ACTION, ensure_label_free
from app.services.relation_proposal_service import relation_texts
from app.utilities.action_text import normalise_action
from app.utilities.artefact_visibility import artefact_company_ids, readable_proposal
from app.utilities.permissions import can_propose, can_read_proposal
from app.utilities.problems import conflict, forbidden, not_found, validation_failed
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

EDITABLE_TYPES = frozenset({ProposalType.CONCEPT, ProposalType.SPEC, ProposalType.RELATION})
MAX_REVISION = 1000
AUDIT_KIND = "edit"
PROPOSAL_CHANGED_EVENT = "proposal.changed"


@dataclass
class _Draft:
    """The pending rows of an editable proposal, with the birth parent of a concept."""

    concept: Concept | None
    relation: Relation | None
    parent: Concept | None


async def edit_proposal(
    session: AsyncSession, caller: Caller, proposal_id: uuid.UUID, body: ProposalEdit
) -> ProposalDto:
    await decision_lock_service.acquire(session, caller.tenant_id)
    proposal = await proposal_repository.get_for_update(session, caller.tenant_id, proposal_id)
    if proposal is None or not can_read_proposal(caller.grants, proposal_company_ids(proposal)):
        raise not_found("proposal")
    if proposal.type not in EDITABLE_TYPES or proposal.state is not ProposalState.PENDING:
        raise conflict(
            "proposal_not_editable",
            f"a {proposal.state.value} {proposal.type.value} proposal cannot be edited",
        )
    open_proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, open_proposals)
    _ensure_can_edit(caller, view, proposal)
    if body.revision != proposal.revision:
        raise conflict(
            "proposal_changed",
            f"the proposal is at revision {proposal.revision}, not {body.revision}",
        )
    if proposal.revision >= MAX_REVISION:
        raise conflict("proposal_not_editable", "the proposal was edited too many times")
    draft = _draft_of(view, proposal)
    old_text = _draft_text(view, proposal, draft)
    old_label = draft.concept.label if draft.concept is not None else None
    changed_concept = False
    changed_relation = False
    if body.label is not None:
        changed_concept = await _apply_label(session, view, proposal, draft, body.label)
    if body.action is not None:
        changed_relation = await _apply_action(session, view, proposal, draft, body.action)
    title, html = _rebuild_texts(view, proposal, draft)
    await proposal_repository.edit_draft(
        session, proposal, title=title, html=html, revision=proposal.revision + 1
    )
    if changed_concept and old_label is not None and draft.concept is not None:
        await _rewrite_dependants(session, view, proposal, open_proposals, draft.concept, old_label)
    await _emit_changes(session, caller, view, proposal, draft, changed_concept, changed_relation)
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        f"{old_text} → {_draft_text(view, proposal, draft)}",
        True,
        proposal.id,
        company_ids=proposal_company_ids(proposal),
        domain_key=view.proposal_domain_key(proposal),
        origin=proposal.origin,
    )
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


def _ensure_can_edit(caller: Caller, view: OntologyView, proposal: Proposal) -> None:
    """The proposer, or anyone who may propose in the proposal's scope."""
    if proposal.proposer_user_id is not None and proposal.proposer_user_id == caller.user_id:
        return
    scopes = view.proposal_scopes(proposal)
    if all(can_propose(caller.grants, scope, caller.everyone_teaches) for scope in scopes):
        return
    raise forbidden("Only the proposer or someone who may propose in this scope can edit it")


def _draft_of(view: OntologyView, proposal: Proposal) -> _Draft:
    concept = view.concepts.get(proposal.concept_id) if proposal.concept_id else None
    relation = view.relations.get(proposal.relation_id) if proposal.relation_id else None
    if proposal.type is ProposalType.RELATION:
        if relation is None:
            raise conflict("proposal_not_editable", "the pending relation no longer exists")
        return _Draft(concept=None, relation=relation, parent=None)
    if concept is None or not concept.pending or relation is None:
        raise conflict("proposal_not_editable", "the pending concept no longer exists")
    parent = view.concepts.get(concept.parent_id) if concept.parent_id else None
    if parent is None:
        raise conflict("proposal_not_editable", "the birth parent no longer exists")
    return _Draft(concept=concept, relation=relation, parent=parent)


async def _apply_label(
    session: AsyncSession, view: OntologyView, proposal: Proposal, draft: _Draft, label: str
) -> bool:
    if proposal.type is ProposalType.RELATION or draft.concept is None:
        raise validation_failed("label", "a relation proposal has no label; edit its action")
    if not label.strip():
        raise validation_failed("label", "a label needs at least one character")
    concept = draft.concept
    if label == concept.label:
        return False
    existing = view.find_label(concept.company_id, label)
    if existing is not None and existing.id != concept.id:
        raise conflict("duplicate_label", f"{label} already exists in this company")
    if label.lower() != concept.label.lower():
        await ensure_label_free(session, view, concept.company_id, label)
    await concept_repository.rename(session, concept, label)
    return True


async def _apply_action(
    session: AsyncSession, view: OntologyView, proposal: Proposal, draft: _Draft, action: str
) -> bool:
    if proposal.type is ProposalType.SPEC:
        raise validation_failed("action", "a specialisation is always `is a`")
    relation = draft.relation
    assert relation is not None
    normalised = normalise_action(action)
    if not normalised:
        raise validation_failed("action", "an action needs at least one word")
    if normalised == normalise_action(relation.label):
        return False
    if relation.kind is not RelationKind.REL:
        raise conflict("structural_relation", f"a {relation.label} relation cannot be relabelled")
    if normalised in (ISA_ACTION, SAME_ACTION):
        raise validation_failed("action", f"`{normalised}` is a structural relation, not an action")
    if any(
        r.id != relation.id
        and r.a_id == relation.a_id
        and r.b_id == relation.b_id
        and normalise_action(r.label) == normalised
        for r in view.live_relations()
    ):
        a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
        raise conflict(
            "duplicate_relation", f"{a.label} {normalised} {b.label} is already in the model"
        )
    await relation_repository.update(
        session, relation, label=normalised, a_id=relation.a_id, b_id=relation.b_id
    )
    if draft.concept is not None:
        await concept_repository.set_birth_action(session, draft.concept, normalised)
    return True


def _rebuild_texts(view: OntologyView, proposal: Proposal, draft: _Draft) -> tuple[str, str]:
    if proposal.type is ProposalType.RELATION:
        assert draft.relation is not None
        a, b = view.concepts[draft.relation.a_id], view.concepts[draft.relation.b_id]
        texts = relation_texts(view, a, b, draft.relation.label)
        return texts.title, texts.html
    assert draft.concept is not None and draft.parent is not None and draft.relation is not None
    concept, parent = draft.concept, draft.parent
    if proposal.type is ProposalType.SPEC:
        return concept.label, spec_panel_html(concept.label, parent.label)
    return concept.label, concept_panel_html(
        concept.label, parent.label, draft.relation.label, concept.birth_reverse
    )


def _draft_text(view: OntologyView, proposal: Proposal, draft: _Draft) -> str:
    """The draft as one sentence, for the audit entry."""
    if proposal.type is ProposalType.RELATION:
        assert draft.relation is not None
        a, b = view.concepts[draft.relation.a_id], view.concepts[draft.relation.b_id]
        return f"{a.label} {draft.relation.label} {b.label}"
    assert draft.concept is not None and draft.parent is not None and draft.relation is not None
    concept, parent, action = draft.concept, draft.parent, draft.relation.label
    if proposal.type is ProposalType.SPEC:
        return f"{concept.label} is a {parent.label}"
    if concept.birth_reverse:
        return f"{concept.label} {action} {parent.label}"
    return f"{parent.label} {action} {concept.label}"


async def _rewrite_dependants(
    session: AsyncSession,
    view: OntologyView,
    proposal: Proposal,
    open_proposals: list[Proposal],
    concept: Concept,
    old_label: str,
) -> None:
    """Open proposals of the company that named the old label wait for the new one; a relation
    proposal touching the concept takes the new ends in its `waitFor`."""
    for q in open_proposals:
        if q.id == proposal.id or q.state is not ProposalState.PENDING:
            continue
        relation = view.relations.get(q.relation_id) if q.relation_id else None
        if (
            q.type is ProposalType.RELATION
            and relation is not None
            and concept.id in (relation.a_id, relation.b_id)
        ):
            a, b = view.concepts.get(relation.a_id), view.concepts.get(relation.b_id)
            if a is not None and b is not None:
                await proposal_repository.rewrite_dependencies(
                    session,
                    q,
                    deps=list(q.deps),
                    wait_for=f"{a.label} and {b.label}",
                    parent_label=q.parent_label,
                )
            continue
        if q.company_id != concept.company_id:
            continue
        deps = [concept.label if str(d) == old_label else d for d in q.deps]
        wait_for = concept.label if q.wait_for == old_label else q.wait_for
        parent_label = concept.label if q.parent_label == old_label else q.parent_label
        if (deps, wait_for, parent_label) != (list(q.deps), q.wait_for, q.parent_label):
            await proposal_repository.rewrite_dependencies(
                session, q, deps=deps, wait_for=wait_for, parent_label=parent_label
            )


async def _emit_changes(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    draft: _Draft,
    changed_concept: bool,
    changed_relation: bool,
) -> None:
    dto = view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    companies = proposal_company_ids(proposal) | (
        artefact_company_ids(dto.artefacts) if dto.artefacts else set()
    )
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        PROPOSAL_CHANGED_EVENT,
        {
            "proposal": dto.model_dump(mode="json", by_alias=True, exclude={"artefacts"}),
            "artefacts": dto.artefacts.model_dump(mode="json", by_alias=True)
            if dto.artefacts
            else {},
            "cascaded": [],
        },
        company_ids=companies,
        bulk=proposal.bulk,
    )
    if changed_concept and draft.concept is not None:
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "concept.changed",
            {
                "concept": view.concept_dto(draft.concept).model_dump(mode="json", by_alias=True),
                "fields": ["label"],
                "proposalId": str(proposal.id),
            },
            company_ids=[draft.concept.company_id],
            bulk=proposal.bulk,
        )
    if changed_relation and draft.relation is not None:
        relation_dto = view.relation_dto(draft.relation)
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "relation.changed",
            {
                "relation": relation_dto.model_dump(mode="json", by_alias=True),
                "fields": ["label"],
                "proposalId": str(proposal.id),
            },
            company_ids=relation_dto.company_ids,
            bulk=proposal.bulk,
        )
