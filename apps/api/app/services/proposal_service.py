"""Creates proposals from typed drafts and writes their pending artefacts at once.

Every ontology mutation endpoint ends here. Creating a proposal writes the pending concept and
its birth relation, or the pending relation, in the same transaction as the proposal row, the
`proposal.created` event and the `concept.born` or `relation.created` event. Nothing here ever
writes an approved row. Panel `html` is built here only: every label is HTML-escaped and the
markup uses `<b>` and `<i>` alone.
"""

from __future__ import annotations

import html
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import (
    AttributeDraft,
    BindingDraft,
    ChangeDraft,
    ConceptDraft,
    RelationDraft,
    SourceDraft,
    SpecDraft,
)
from app.models.storage.base import ActorKind, ChangeKind, NodeKind, ProposalType, RelationKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.repositories import concept_repository, proposal_repository, relation_repository
from app.services import outbox_service
from app.services.ontology_view_service import PREDICATE_BOTH_ENDS_APPROVED, OntologyView
from app.utilities.clock import get_clock
from app.utilities.layout import (
    CONFLICT_COLOR,
    NEUTRAL_COLOR,
    birth_position,
    company_centre,
    domain_centre,
    rest_length,
)
from app.utilities.permissions import Scope, can_propose
from app.utilities.problems import (
    ProblemError,
    conflict,
    forbidden,
    not_found,
    validation_failed,
)
from app.utilities.randomness import get_randomness

logger = logging.getLogger(__name__)

ISA_ACTION = "is a"
SAME_ACTION = "equivalent to"
STRUCTURAL_KINDS = frozenset({RelationKind.ISA, RelationKind.SAME})
UNAVAILABLE_CHANGE_KINDS = frozenset(
    {"unbind", "rename_source", "remove_source", "resolve_conflict"}
)

Draft = (
    ConceptDraft
    | SpecDraft
    | RelationDraft
    | SourceDraft
    | BindingDraft
    | AttributeDraft
    | ChangeDraft
)


async def create(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    draft: Draft,
    *,
    bulk: bool = False,
    enforce_permission: bool = True,
    proposer: Actor | None = None,
) -> Proposal:
    """Create one proposal with its pending artefacts; refusals are Problem+JSON errors.

    `proposer` defaults to the caller; the starter vocabulary passes the system actor.
    """
    who = proposer or caller.actor
    match draft:
        case ConceptDraft():
            return await _propose_concept(
                session, caller, who, view, draft, bulk, enforce_permission
            )
        case SpecDraft():
            return await _propose_spec(session, caller, who, view, draft, bulk, enforce_permission)
        case RelationDraft():
            return await _propose_relation(
                session, caller, who, view, draft, bulk, enforce_permission
            )
        case ChangeDraft():
            return await _propose_change(
                session, caller, who, view, draft, bulk, enforce_permission
            )
        case _:
            raise ProblemError(
                503, "unavailable", f"{draft.type} proposals are served by the bindings module"
            )


async def create_batch(
    session: AsyncSession, caller: Caller, view: OntologyView, drafts: list[Draft]
) -> list[Proposal]:
    """Create drafts in order so later ones may name labels introduced by earlier ones."""
    return [await create(session, caller, view, draft) for draft in drafts]


async def propose_equivalence(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    caption: str | None,
) -> Proposal:
    """A `same` relation between two companies' concepts."""
    a, b = view.concepts.get(a_id), view.concepts.get(b_id)
    if a is None or b is None:
        raise not_found("concept")
    if a.company_id == b.company_id:
        raise conflict("same_company", "both concepts belong to one company")
    draft = RelationDraft(a_id=a_id, b_id=b_id, action=SAME_ACTION, caption=caption)
    return await _propose_relation(session, caller, caller.actor, view, draft, False, True)


# ---------------------------------------------------------------------------- concepts


async def _propose_concept(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ConceptDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    company, parent, product = _resolve_birth(
        view, draft.company_id, draft.parent_id, draft.parent_label, draft.domain_key
    )
    if enforce:
        _ensure_can_propose(caller, Scope(company.id, product.template_key))
    _ensure_label_free(view, company.id, draft.label)
    template = view.templates[product.template_key]
    action = draft.action.strip().lower()
    concept, relation = await _divide(
        session,
        view,
        company,
        parent,
        product,
        draft.label,
        rule=None,
        isa=False,
        action=action,
        reverse=draft.reverse,
        seed=draft.seed,
    )
    label, parent_label, pred = _esc(draft.label), _esc(parent.label), _esc(action)
    if draft.reverse:
        html_text = f"<b>{label}</b> <i>· {label} <b>{pred}</b> {parent_label}</i>"
    else:
        html_text = f"<b>{label}</b> <i>· {parent_label} <b>{pred}</b> {label}</i>"
    proposal = await _store(
        session,
        proposer,
        view,
        type=ProposalType.CONCEPT,
        change_kind=None,
        title=draft.label,
        color=view.effective_color(template.key),
        company_id=company.id,
        domain_product_id=product.id,
        parent_label=parent.label,
        deps=[parent.label],
        wait_for=parent.label,
        html=html_text,
        why=f"domain product: {template.name}",
        caption=draft.caption,
        payload={},
        concept_id=concept.id,
        relation_id=relation.id,
        bulk=bulk,
    )
    await _emit_born(session, proposer, view, proposal, concept, relation)
    return proposal


async def _propose_spec(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: SpecDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    company, parent, product = _resolve_birth(
        view, draft.company_id, draft.parent_id, draft.parent_label, draft.domain_key
    )
    if enforce:
        _ensure_can_propose(caller, Scope(company.id, product.template_key))
    _ensure_label_free(view, company.id, draft.label)
    template = view.templates[product.template_key]
    concept, relation = await _divide(
        session,
        view,
        company,
        parent,
        product,
        draft.label,
        rule=draft.rule,
        isa=True,
        action=ISA_ACTION,
        reverse=False,
        seed=draft.seed,
    )
    why = (f"rule: {draft.rule}" if draft.rule else "") + f" · domain product: {template.name}"
    proposal = await _store(
        session,
        proposer,
        view,
        type=ProposalType.SPEC,
        change_kind=None,
        title=draft.label,
        color=view.effective_color(template.key),
        company_id=company.id,
        domain_product_id=product.id,
        parent_label=parent.label,
        deps=[parent.label],
        wait_for=parent.label,
        html=f"<b>{_esc(draft.label)}</b> <i>is a {_esc(parent.label)}</i>",
        why=why,
        caption=draft.caption,
        payload={},
        concept_id=concept.id,
        relation_id=relation.id,
        bulk=bulk,
    )
    await _emit_born(session, proposer, view, proposal, concept, relation)
    return proposal


async def _divide(
    session: AsyncSession,
    view: OntologyView,
    company: Company,
    parent: Concept,
    product: Any,
    label: str,
    *,
    rule: str | None,
    isa: bool,
    action: str,
    reverse: bool,
    seed: float | None,
) -> tuple[Concept, Relation]:
    """Write the pending cell born from `parent` and its pending birth relation."""
    rng, clock = get_randomness(), get_clock()
    template = view.templates[product.template_key]
    company_xy = company_centre(company.position, len(view.companies))
    x, y = birth_position(
        (parent.x, parent.y), domain_centre(company_xy, template.position), rng.next()
    )
    concept = await concept_repository.create(
        session,
        tenant_id=view.tenant_id,
        company_id=company.id,
        kind=NodeKind.CONCEPT,
        label=label,
        sub=rule or "",
        domain_product_id=product.id,
        rule=rule,
        pending=True,
        parent_id=parent.id,
        birth_action=action,
        birth_reverse=reverse,
        born_at=clock.now(),
        x=x,
        y=y,
    )
    view.register_concept(concept)
    cross_domain = parent.domain_product_id != product.id
    kind = RelationKind.ISA if isa else RelationKind.REL
    a, b = (concept, parent) if (isa or reverse) else (parent, concept)
    relation = await relation_repository.create(
        session,
        tenant_id=view.tenant_id,
        a_id=a.id,
        b_id=b.id,
        kind=kind,
        label=action,
        rest=rest_length(kind.value, cross_domain, False),
        seed=seed if seed is not None else rng.next(),
        pending=True,
    )
    view.register_relation(relation)
    concept.birth_relation_id = relation.id
    await session.flush()
    return concept, relation


def _resolve_birth(
    view: OntologyView,
    company_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    parent_label: str | None,
    domain_key: str,
) -> tuple[Company, Concept, Any]:
    company = view.companies.get(company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if parent_id is not None:
        parent = view.concepts.get(parent_id)
        if parent is None or parent.company_id != company.id or parent.dying_at is not None:
            raise not_found("parent concept")
    else:
        parent = view.find_label(company.id, parent_label or "")
        if parent is None:
            raise not_found(f"parent concept {parent_label!r}")
    product = view.domain_product_by_key(company.id, domain_key)
    if product is None:
        raise validation_failed("domainKey", f"unknown domain key {domain_key!r}")
    return company, parent, product


def _ensure_label_free(view: OntologyView, company_id: uuid.UUID, label: str) -> None:
    if view.find_label(company_id, label) is not None:
        raise conflict("duplicate_label", f"{label} already exists in this company")


# ---------------------------------------------------------------------------- relations


async def _propose_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: RelationDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    a = _resolve_end(view, draft.a_id, draft.a_label, draft.company_id)
    b = _resolve_end(view, draft.b_id, draft.b_label, draft.company_id)
    if a.id == b.id:
        raise validation_failed("bId", "a relation needs two different concepts")
    action = draft.action.strip().lower()
    cross_company = a.company_id != b.company_id
    if cross_company and not (view.settings and view.settings.cross_company):
        raise conflict(
            "cross_company_disabled", "companies may not interact · enable it in the admin portal"
        )
    if enforce:
        _ensure_can_propose(caller, Scope(a.company_id, view.domain_key(a)))
    if any(
        r.a_id == a.id and r.b_id == b.id and r.label.lower() == action
        for r in view.live_relations()
    ):
        raise conflict(
            "duplicate_relation", f"{a.label} {action} {b.label} is already in the model"
        )
    kind = _relation_kind(action)
    cross_domain = a.domain_product_id != b.domain_product_id
    relation = await relation_repository.create(
        session,
        tenant_id=view.tenant_id,
        a_id=a.id,
        b_id=b.id,
        kind=kind,
        label=action,
        rest=rest_length(kind.value, cross_domain, cross_company),
        seed=draft.seed if draft.seed is not None else get_randomness().next(),
        pending=True,
    )
    view.register_relation(relation)
    company_a, company_b = view.companies[a.company_id], view.companies[b.company_id]
    a_text = _esc(a.label) + (f" <i>({_esc(company_a.name)})</i>" if cross_company else "")
    b_text = _esc(b.label) + (f" <i>({_esc(company_b.name)})</i>" if cross_company else "")
    if cross_company:
        why = f"across companies: {company_a.name} ↔ {company_b.name}"
    elif cross_domain:
        why = (
            f"across domain products: {view.domain_name(a) or 'company'}"
            f" → {view.domain_name(b) or 'company'}"
        )
    else:
        why = f"inside {view.domain_name(a) or 'the company'}"
    proposal = await _store(
        session,
        proposer,
        view,
        type=ProposalType.RELATION,
        change_kind=None,
        title=f"{a.label} {action} {b.label}",
        color=NEUTRAL_COLOR,
        company_id=a.company_id,
        domain_product_id=a.domain_product_id,
        parent_label=None,
        deps=[PREDICATE_BOTH_ENDS_APPROVED],
        wait_for=f"{a.label} and {b.label}",
        html=f"{a_text} <b>{_esc(action)}</b> {b_text}",
        why=why,
        caption=draft.caption,
        payload={},
        concept_id=None,
        relation_id=relation.id,
        bulk=bulk,
    )
    await outbox_service.emit(
        session,
        view.tenant_id,
        proposer,
        "relation.created",
        {
            "relation": view.relation_dto(relation).model_dump(mode="json", by_alias=True),
            "proposalId": str(proposal.id),
        },
        company_id=a.company_id,
        bulk=bulk,
    )
    return proposal


def _resolve_end(
    view: OntologyView,
    concept_id: uuid.UUID | None,
    label: str | None,
    company_id: uuid.UUID | None,
) -> Concept:
    if concept_id is not None:
        concept = view.concepts.get(concept_id)
        if concept is None or concept.dying_at is not None:
            raise not_found("concept")
        return concept
    if company_id is None or company_id not in view.companies:
        raise not_found("company")
    concept = view.find_label(company_id, label or "")
    if concept is None:
        raise not_found(f"concept {label!r}")
    return concept


def _relation_kind(action: str) -> RelationKind:
    if action == ISA_ACTION:
        return RelationKind.ISA
    if action == SAME_ACTION:
        return RelationKind.SAME
    return RelationKind.REL


# ---------------------------------------------------------------------------- changes


async def _propose_change(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    if draft.change_kind in UNAVAILABLE_CHANGE_KINDS:
        raise ProblemError(
            503, "unavailable", f"{draft.change_kind} changes are served by the bindings module"
        )
    match draft.change_kind:
        case "rename":
            return await _propose_rename(session, caller, proposer, view, draft, bulk, enforce)
        case "delete_concept":
            return await _propose_delete_concept(
                session, caller, proposer, view, draft, bulk, enforce
            )
        case "edit_relation":
            return await _propose_edit_relation(
                session, caller, proposer, view, draft, bulk, enforce
            )
        case "remove_relation":
            return await _propose_remove_relation(
                session, caller, proposer, view, draft, bulk, enforce
            )
        case _:
            return await _propose_remove_company(
                session, caller, proposer, view, draft, bulk, enforce
            )


async def _propose_rename(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    concept = _payload_concept(view, draft.payload.concept_id)
    new_label = (draft.payload.new_label or "").strip()
    if not new_label:
        raise validation_failed("payload.newLabel", "newLabel is required")
    if new_label == concept.label:
        raise validation_failed("payload.newLabel", "the new label equals the current one")
    if enforce:
        _ensure_can_propose(caller, Scope(concept.company_id, view.domain_key(concept)))
    existing = view.find_label(concept.company_id, new_label)
    if existing is not None and existing.id != concept.id:
        raise conflict("duplicate_label", f"{new_label} already exists in this company")
    relations = len(view.relations_touching(concept.id))
    return await _store(
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
        html=f"Rename <b>{_esc(concept.label)}</b> to <b>{_esc(new_label)}</b>",
        why=f"{relations} relations keep pointing at it",
        caption=draft.caption or f"{concept.label} is now called {new_label}.",
        payload={"conceptId": str(concept.id), "newLabel": new_label},
        concept_id=None,
        relation_id=None,
        bulk=bulk,
    )


async def _propose_delete_concept(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    concept = _payload_concept(view, draft.payload.concept_id)
    if enforce:
        _ensure_can_propose(caller, Scope(concept.company_id, view.domain_key(concept)))
    relations = len(view.relations_touching(concept.id))
    plural = "" if relations == 1 else "s"
    return await _store(
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
        html=f"Delete <b>{_esc(concept.label)}</b> and its {relations} relation{plural}",
        why="specialisations of it are deleted too",
        caption=draft.caption or f"{concept.label} was removed from the model.",
        payload={"conceptId": str(concept.id)},
        concept_id=None,
        relation_id=None,
        bulk=bulk,
    )


async def _propose_edit_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    relation = _payload_relation(view, draft.payload.relation_id)
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    reverse = bool(draft.payload.reverse)
    action = (draft.payload.action or relation.label).strip().lower()
    if action == relation.label and not reverse:
        raise validation_failed("payload", "nothing changes: same action and same direction")
    if action != relation.label and relation.kind in STRUCTURAL_KINDS:
        raise conflict("structural_relation", f"a {relation.label} relation cannot be relabelled")
    if enforce:
        _ensure_can_propose(caller, Scope(a.company_id, view.domain_key(a)))
    frm, to = (b, a) if reverse else (a, b)
    if any(
        r.id != relation.id and r.a_id == frm.id and r.b_id == to.id and r.label.lower() == action
        for r in view.live_relations()
    ):
        raise conflict(
            "duplicate_relation", f"{frm.label} {action} {to.label} is already in the model"
        )
    return await _store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.EDIT_RELATION,
        title=f"{frm.label} {action} {to.label}",
        color=NEUTRAL_COLOR,
        company_id=a.company_id,
        domain_product_id=frm.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Relation <b>{_esc(a.label)}</b> <i>{_esc(relation.label)}</i> {_esc(b.label)}"
            " becomes "
            f"<b>{_esc(frm.label)}</b> <i>{_esc(action)}</i> {_esc(to.label)}"
        ),
        why="direction reversed" if reverse else "action renamed",
        caption=draft.caption or f"The relation now reads {frm.label} {action} {to.label}.",
        payload={"relationId": str(relation.id), "action": action, "reverse": reverse},
        concept_id=None,
        relation_id=None,
        bulk=bulk,
    )


async def _propose_remove_relation(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    relation = _payload_relation(view, draft.payload.relation_id)
    if relation.kind is RelationKind.CLASH:
        raise conflict("structural_relation", "a conflict leaves through its resolution")
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    if enforce:
        _ensure_can_propose(caller, Scope(a.company_id, view.domain_key(a)))
    if relation.kind is RelationKind.ISA:
        why = "the specialisation would no longer inherit from its parent"
    elif relation.kind is RelationKind.SAME:
        why = "the two vocabularies would no longer be aligned on this concept"
    else:
        why = "action removed from the model"
    return await _store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.REMOVE_RELATION,
        title=f"Remove {a.label} {relation.label} {b.label}",
        color=CONFLICT_COLOR,
        company_id=a.company_id,
        domain_product_id=a.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Remove the relation <b>{_esc(a.label)}</b> <i>{_esc(relation.label)}</i>"
            f" {_esc(b.label)}"
        ),
        why=why,
        caption=draft.caption
        or f"{a.label} {relation.label} {b.label} was removed from the model.",
        payload={"relationId": str(relation.id)},
        concept_id=None,
        relation_id=None,
        bulk=bulk,
    )


async def _propose_remove_company(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
) -> Proposal:
    company = view.companies.get(draft.payload.company_id or uuid.UUID(int=0))
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if company.is_home:
        raise conflict("home_company", "the home company cannot be removed")
    if enforce:
        _ensure_can_propose(caller, Scope(company.id, None))
    cells = sum(1 for c in view.live_concepts() if c.company_id == company.id)
    return await _store(
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
        html=f"Remove <b>{_esc(company.name)}</b> from the portfolio with its {cells} cells",
        why="equivalences to other companies are removed too",
        caption=draft.caption or f"{company.name} left the view.",
        payload={"companyId": str(company.id)},
        concept_id=None,
        relation_id=None,
        bulk=bulk,
    )


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


# ---------------------------------------------------------------------------- shared


def _esc(value: str) -> str:
    """HTML-escape a label before it enters the panel markup."""
    return html.escape(value, quote=True)


def _ensure_can_propose(caller: Caller, scope: Scope) -> None:
    if not can_propose(caller.grants, scope, caller.everyone_teaches):
        raise forbidden("your roles do not allow proposing in this scope")


async def _store(
    session: AsyncSession,
    proposer: Actor,
    view: OntologyView,
    *,
    type: ProposalType,
    change_kind: ChangeKind | None,
    title: str,
    color: str,
    company_id: uuid.UUID | None,
    domain_product_id: uuid.UUID | None,
    parent_label: str | None,
    deps: list[str],
    wait_for: str | None,
    html: str,
    why: str | None,
    caption: str | None,
    payload: dict[str, Any],
    concept_id: uuid.UUID | None,
    relation_id: uuid.UUID | None,
    bulk: bool,
) -> Proposal:
    proposal = await proposal_repository.create(
        session,
        tenant_id=view.tenant_id,
        type=type,
        change_kind=change_kind,
        title=title,
        color=color,
        company_id=company_id,
        domain_product_id=domain_product_id,
        parent_label=parent_label,
        deps=deps,
        wait_for=wait_for,
        html=html,
        why=why or None,
        caption=caption,
        payload=payload,
        concept_id=concept_id,
        relation_id=relation_id,
        relation_ids=[],
        proposer_kind=ActorKind(proposer.kind),
        proposer_user_id=proposer.id if proposer.kind == "user" else None,
        bulk=bulk,
    )
    dto = view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    await outbox_service.emit(
        session,
        view.tenant_id,
        proposer,
        "proposal.created",
        {
            "proposal": dto.model_dump(mode="json", by_alias=True, exclude={"artefacts"}),
            "artefacts": dto.artefacts.model_dump(mode="json", by_alias=True)
            if dto.artefacts
            else {},
            "cascaded": [],
        },
        company_id=company_id,
        bulk=bulk,
    )
    return proposal


async def _emit_born(
    session: AsyncSession,
    proposer: Actor,
    view: OntologyView,
    proposal: Proposal,
    concept: Concept,
    relation: Relation,
) -> None:
    await outbox_service.emit(
        session,
        view.tenant_id,
        proposer,
        "concept.born",
        {
            "concept": view.concept_dto(concept).model_dump(mode="json", by_alias=True),
            "birthRelation": view.relation_dto(relation).model_dump(mode="json", by_alias=True),
            "proposalId": str(proposal.id),
        },
        company_id=concept.company_id,
        bulk=proposal.bulk,
    )
