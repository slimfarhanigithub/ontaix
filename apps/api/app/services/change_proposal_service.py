"""Change proposals: rename, delete a concept, edit or remove a relation, remove a company.

A change proposal writes no pending artefact: it points at the live row it would change through
its payload, and the row changes only when the proposal is approved. A change to a relation
between two companies is a tenant-level proposal, exactly like the relation itself.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import ChangeDraft
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.base import ChangeKind, NodeKind, ProposalType, RelationKind
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import (
    ensure_can_propose,
    ensure_company_still_live,
    ensure_relation_still_live,
    ensure_still_live,
    esc,
    store,
)
from app.utilities.action_text import normalise_action
from app.utilities.layout import CONFLICT_COLOR, NEUTRAL_COLOR
from app.utilities.permissions import Scope
from app.utilities.problems import ProblemError, conflict, not_found, validation_failed

logger = logging.getLogger(__name__)

STRUCTURAL_KINDS = frozenset({RelationKind.ISA, RelationKind.SAME})
UNAVAILABLE_CHANGE_KINDS = frozenset(
    {"unbind", "rename_source", "remove_source", "resolve_conflict"}
)


async def propose_change(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    if draft.change_kind in UNAVAILABLE_CHANGE_KINDS:
        raise ProblemError(
            503, "unavailable", f"{draft.change_kind} changes are served by the bindings module"
        )
    match draft.change_kind:
        case "rename":
            return await _propose_rename(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case "delete_concept":
            return await _propose_delete_concept(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case "edit_relation":
            return await _propose_edit_relation(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case "remove_relation":
            return await _propose_remove_relation(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case _:
            return await _propose_remove_company(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )


async def _propose_rename(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    concept = _payload_concept(view, draft.payload.concept_id)
    new_label = (draft.payload.new_label or "").strip()
    if not new_label:
        raise validation_failed("payload.newLabel", "newLabel is required")
    if new_label == concept.label:
        raise validation_failed("payload.newLabel", "the new label equals the current one")
    if enforce:
        ensure_can_propose(caller, Scope(concept.company_id, view.domain_key(concept)))
    await ensure_still_live(session, view, concept)
    existing = view.find_label(concept.company_id, new_label)
    if existing is not None and existing.id != concept.id:
        raise conflict("duplicate_label", f"{new_label} already exists in this company")
    relations = len(view.relations_touching(concept.id))
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.RENAME,
        title=f"Rename {concept.label} to {new_label}",
        color=view.concept_color(concept),
        company_id=concept.company_id,
        domain_product_id=concept.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Rename <b>{esc(concept.label)}</b> to <b>{esc(new_label)}</b>",
        why=f"{relations} relations keep pointing at it",
        caption=draft.caption or f"{concept.label} is now called {new_label}.",
        payload={"conceptId": str(concept.id), "newLabel": new_label},
        touched_company_ids=[concept.company_id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_delete_concept(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    concept = _payload_concept(view, draft.payload.concept_id)
    if enforce:
        ensure_can_propose(caller, Scope(concept.company_id, view.domain_key(concept)))
    await ensure_still_live(session, view, concept)
    relations = len(view.relations_touching(concept.id))
    plural = "" if relations == 1 else "s"
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.DELETE_CONCEPT,
        title=f"Delete {concept.label}",
        color=CONFLICT_COLOR,
        company_id=concept.company_id,
        domain_product_id=concept.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Delete <b>{esc(concept.label)}</b> and its {relations} relation{plural}",
        why="specialisations of it are deleted too",
        caption=draft.caption or f"{concept.label} was removed from the model.",
        payload={"conceptId": str(concept.id)},
        touched_company_ids=[concept.company_id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_edit_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    relation = _payload_relation(view, draft.payload.relation_id)
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    reverse = bool(draft.payload.reverse)
    action = normalise_action(draft.payload.action or relation.label)
    if not action:
        raise validation_failed("payload.action", "an action needs at least one word")
    current = normalise_action(relation.label)
    if action == current and not reverse:
        raise validation_failed("payload", "nothing changes: same action and same direction")
    if action != current and relation.kind in STRUCTURAL_KINDS:
        raise conflict("structural_relation", f"a {relation.label} relation cannot be relabelled")
    if enforce:
        _ensure_can_propose_on_ends(caller, view, a, b)
    await ensure_relation_still_live(session, view, relation)
    frm, to = (b, a) if reverse else (a, b)
    if any(
        r.id != relation.id
        and r.a_id == frm.id
        and r.b_id == to.id
        and normalise_action(r.label) == action
        for r in view.live_relations()
    ):
        raise conflict(
            "duplicate_relation", f"{frm.label} {action} {to.label} is already in the model"
        )
    cross_company = a.company_id != b.company_id
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.EDIT_RELATION,
        title=f"{frm.label} {action} {to.label}",
        color=NEUTRAL_COLOR,
        company_id=None if cross_company else a.company_id,
        domain_product_id=None if cross_company else frm.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Relation <b>{esc(a.label)}</b> <i>{esc(relation.label)}</i> {esc(b.label)}"
            " becomes "
            f"<b>{esc(frm.label)}</b> <i>{esc(action)}</i> {esc(to.label)}"
        ),
        why="direction reversed" if reverse else "action renamed",
        caption=draft.caption or f"The relation now reads {frm.label} {action} {to.label}.",
        payload={"relationId": str(relation.id), "action": action, "reverse": reverse},
        touched_company_ids=[a.company_id, b.company_id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_remove_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    relation = _payload_relation(view, draft.payload.relation_id)
    if relation.kind is RelationKind.CLASH:
        raise conflict("structural_relation", "a conflict leaves through its resolution")
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    if enforce:
        _ensure_can_propose_on_ends(caller, view, a, b)
    await ensure_relation_still_live(session, view, relation)
    if relation.kind is RelationKind.ISA:
        why = "the specialisation would no longer inherit from its parent"
    elif relation.kind is RelationKind.SAME:
        why = "the two vocabularies would no longer be aligned on this concept"
    else:
        why = "action removed from the model"
    cross_company = a.company_id != b.company_id
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.REMOVE_RELATION,
        title=f"Remove {a.label} {relation.label} {b.label}",
        color=CONFLICT_COLOR,
        company_id=None if cross_company else a.company_id,
        domain_product_id=None if cross_company else a.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Remove the relation <b>{esc(a.label)}</b> <i>{esc(relation.label)}</i> {esc(b.label)}"
        ),
        why=why,
        caption=draft.caption
        or f"{a.label} {relation.label} {b.label} was removed from the model.",
        payload={"relationId": str(relation.id)},
        touched_company_ids=[a.company_id, b.company_id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_remove_company(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance = TYPED_TEXT,
) -> Proposal:
    company = view.companies.get(draft.payload.company_id or uuid.UUID(int=0))
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if company.is_home:
        raise conflict("home_company", "the home company cannot be removed")
    if enforce:
        ensure_can_propose(caller, Scope(company.id, None))
    await ensure_company_still_live(session, view, company)
    cells = sum(1 for c in view.live_concepts() if c.company_id == company.id)
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.REMOVE_COMPANY,
        title=f"Remove {company.name}",
        color=CONFLICT_COLOR,
        company_id=company.id,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Remove <b>{esc(company.name)}</b> from the portfolio with its {cells} cells",
        why="equivalences to other companies are removed too",
        caption=draft.caption or f"{company.name} left the view.",
        payload={"companyId": str(company.id)},
        touched_company_ids=[company.id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


def _ensure_can_propose_on_ends(caller: Caller, view: OntologyView, a: Concept, b: Concept) -> None:
    ensure_can_propose(caller, Scope(a.company_id, view.domain_key(a)))
    if b.company_id != a.company_id:
        ensure_can_propose(caller, Scope(b.company_id, view.domain_key(b)))


def _payload_concept(view: OntologyView, concept_id: uuid.UUID | None) -> Concept:
    if concept_id is None:
        raise validation_failed("payload.conceptId", "conceptId is required")
    concept = view.concepts.get(concept_id)
    if concept is None or concept.dying_at is not None:
        raise not_found("concept")
    if concept.kind is NodeKind.ROOT:
        raise conflict("root_concept", "the company root cannot be changed")
    return concept


def _payload_relation(view: OntologyView, relation_id: uuid.UUID | None) -> Relation:
    if relation_id is None:
        raise validation_failed("payload.relationId", "relationId is required")
    relation = view.relations.get(relation_id)
    if relation is None or relation.dying_at is not None:
        raise not_found("relation")
    return relation
