"""Domain change proposals: create a domain, edit a domain, move a concept to another domain.

A domain is tenant-wide, so creating or editing one is a tenant-level proposal with no company
audience: `create_domain` is decided at tenant scope, `edit_domain` in the domain's scope, which
covers it in every company. A move is a proposal of the concept's company, carried by its
source domain product and decided in both the source and the target domain scope. Nothing
changes before approval: the domain row, the colour override and the concept's product are
written by `apply`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

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
from app.models.storage.tenant_domain import TenantDomain
from app.repositories import (
    concept_repository,
    domain_product_repository,
    tenant_domain_repository,
    tenant_settings_repository,
)
from app.services import outbox_service
from app.services.appearance_service import appearance_dto
from app.services.domain_membership_service import domain_product_for
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import ensure_can_propose, ensure_still_live, esc, store
from app.utilities.domain_key import (
    MAX_DOMAINS,
    derive_domain_key,
    domain_name_problem,
    domain_owner_problem,
    same_name,
)
from app.utilities.layout import birth_position, company_centre, domain_centre
from app.utilities.permissions import Scope
from app.utilities.problems import conflict, not_found, validation_failed
from app.utilities.randomness import get_randomness

logger = logging.getLogger(__name__)

DOMAIN_CHANGED_EVENT = "domain.changed"
APPEARANCE_CHANGED_EVENT = "appearance.changed"
MOVE_WHY = "children, relations and bindings stay as they are"


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
    match draft.change_kind:
        case "create_domain":
            return await _propose_create_domain(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case "edit_domain":
            return await _propose_edit_domain(
                session, caller, proposer, view, draft, bulk, enforce, provenance
            )
        case _:
            return await _propose_move_concept(
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
    match proposal.change_kind:
        case ChangeKind.CREATE_DOMAIN:
            return await _apply_create_domain(session, caller, view, proposal, bulk)
        case ChangeKind.EDIT_DOMAIN:
            return await _apply_edit_domain(session, caller, view, proposal, bulk)
        case _:
            return await _apply_move_concept(session, caller, view, proposal, bulk)


async def _propose_create_domain(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance,
) -> Proposal:
    name = _checked_name(draft.payload.name)
    owner = _checked_owner(draft.payload.owner)
    color = draft.payload.color
    if color is None:
        raise validation_failed("payload.color", "color is required")
    if enforce:
        ensure_can_propose(caller, Scope.tenant())
    _ensure_room(view)
    _ensure_name_free(view, name, None)
    key = derive_domain_key(name, view.domains)
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.CREATE_DOMAIN,
        title=f"New domain {name}",
        color=color,
        company_id=None,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Create the domain <b>{esc(name)}</b> for every company",
        why=f"owner: {owner}" if owner else "no owner yet",
        caption=draft.caption or f"{name} is a domain of every company.",
        payload={"key": key, "name": name, "color": color, "owner": owner},
        touched_company_ids=[],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_edit_domain(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance,
) -> Proposal:
    domain = _payload_domain(view, draft.payload.domain_key)
    changes: dict[str, Any] = {}
    if draft.payload.name is not None:
        name = _checked_name(draft.payload.name)
        if name != domain.name:
            _ensure_name_free(view, name, domain.key)
            changes["name"] = name
    if draft.payload.color is not None and draft.payload.color != view.effective_color(domain.key):
        changes["color"] = draft.payload.color
    if draft.payload.owner is not None:
        owner = _checked_owner(draft.payload.owner)
        if owner != domain.owner:
            changes["owner"] = owner
    if not changes:
        raise validation_failed("payload", "nothing changes: same name, colour and owner")
    if enforce:
        ensure_can_propose(caller, Scope(None, domain.key))
    parts: list[str] = []
    if "name" in changes:
        parts.append(f"rename it <b>{esc(changes['name'])}</b>")
    if "color" in changes:
        parts.append(f"colour it <i>{esc(changes['color'])}</i>")
    if "owner" in changes:
        parts.append(f"give it to <i>{esc(changes['owner'] or 'nobody')}</i>")
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.EDIT_DOMAIN,
        title=f"Edit domain {domain.name}",
        color=changes.get("color") or view.effective_color(domain.key),
        company_id=None,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Domain <b>{esc(domain.name)}</b>: " + ", ".join(parts) + " in every company",
        why="a domain is the same in every company",
        caption=draft.caption or f"{changes.get('name') or domain.name} changed in every company.",
        payload={"domainKey": domain.key, **changes},
        touched_company_ids=[],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _propose_move_concept(
    session: AsyncSession,
    caller: Caller,
    proposer: Actor,
    view: OntologyView,
    draft: ChangeDraft,
    bulk: bool,
    enforce: bool,
    provenance: Provenance,
) -> Proposal:
    concept = _payload_concept(view, draft.payload.concept_id)
    if draft.payload.domain_key is None:
        raise validation_failed("payload.domainKey", "domainKey is required")
    target = view.domains.get(draft.payload.domain_key)
    if target is None:
        raise validation_failed(
            "payload.domainKey", f"unknown domain key {draft.payload.domain_key!r}"
        )
    source_key = view.domain_key(concept)
    if source_key == target.key:
        raise validation_failed("payload.domainKey", f"{concept.label} is in {target.name}")
    if enforce:
        ensure_can_propose(caller, Scope(concept.company_id, source_key))
        ensure_can_propose(caller, Scope(concept.company_id, target.key))
    await ensure_still_live(session, view, concept)
    source_name = view.domain_name(concept) or "the company"
    return await store(
        session,
        proposer,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.MOVE_CONCEPT_DOMAIN,
        title=f"Move {concept.label} to {target.name}",
        color=view.effective_color(target.key),
        company_id=concept.company_id,
        domain_product_id=concept.domain_product_id,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=(
            f"Move <b>{esc(concept.label)}</b> from <i>{esc(source_name)}</i>"
            f" to <i>{esc(target.name)}</i>"
        ),
        why=MOVE_WHY,
        caption=draft.caption or f"{concept.label} joined {target.name}.",
        payload={"conceptId": str(concept.id), "domainKey": target.key},
        touched_company_ids=[concept.company_id],
        concept_id=None,
        relation_id=None,
        bulk=bulk,
        provenance=provenance,
    )


async def _apply_create_domain(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> DecisionOutcome:
    name = str(proposal.payload["name"])
    _ensure_room(view)
    _ensure_name_free(view, name, None)
    key = str(proposal.payload.get("key") or "")
    if not key or key in view.domains:
        key = derive_domain_key(name, view.domains)
    domain = await tenant_domain_repository.create(
        session,
        view.tenant_id,
        key=key,
        name=name,
        owner=str(proposal.payload.get("owner") or ""),
        color=str(proposal.payload["color"]),
        position=await tenant_domain_repository.next_position(session, view.tenant_id),
        proposal_id=proposal.id,
    )
    view.domains[domain.key] = domain
    await _emit_domain_changed(session, caller, view, domain, created=True, bulk=bulk)
    return DecisionOutcome(artefacts=Artefacts())


async def _apply_edit_domain(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> DecisionOutcome:
    domain = view.domains.get(str(proposal.payload.get("domainKey") or ""))
    if domain is None:
        raise conflict("proposal_not_ready", "the domain no longer exists")
    payload = proposal.payload
    name = str(payload.get("name") or domain.name)
    if name != domain.name:
        _ensure_name_free(view, name, domain.key)
    owner = str(payload["owner"]) if "owner" in payload else domain.owner
    color = str(payload.get("color") or view.effective_color(domain.key))
    recoloured = color != view.effective_color(domain.key)
    await tenant_domain_repository.update(
        session, domain, name=name, owner=owner, color=color, proposal_id=proposal.id
    )
    if recoloured:
        settings = view.settings
        if settings is None:
            settings = await tenant_settings_repository.create(session, view.tenant_id)
            view.settings = settings
        await tenant_settings_repository.set_color(session, settings, domain.key, color)
    await _emit_domain_changed(session, caller, view, domain, created=False, bulk=bulk)
    if recoloured:
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            APPEARANCE_CHANGED_EVENT,
            {
                "appearance": appearance_dto(view, view.settings).model_dump(
                    mode="json", by_alias=True
                ),
                "changed": ["colors"],
            },
            company_ids=[],
            bulk=bulk,
        )
    return DecisionOutcome(artefacts=Artefacts())


async def _apply_move_concept(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal, bulk: bool
) -> DecisionOutcome:
    concept = view.concepts.get(uuid.UUID(str(proposal.payload["conceptId"])))
    if concept is None or concept.dying_at is not None:
        raise conflict("proposal_not_ready", "the concept no longer exists")
    target = view.domains.get(str(proposal.payload.get("domainKey") or ""))
    if target is None:
        raise conflict("proposal_not_ready", "the domain no longer exists")
    if view.domain_key(concept) == target.key:
        raise conflict("proposal_not_ready", f"{concept.label} is in {target.name} already")
    company = view.companies[concept.company_id]
    product = await domain_product_for(session, view, company.id, target.key)
    parent = view.concepts.get(concept.parent_id) if concept.parent_id else None
    origin = (parent.x, parent.y) if parent is not None else (concept.x, concept.y)
    company_xy = company_centre(company.position, len(view.companies))
    x, y = birth_position(
        origin, domain_centre(company_xy, target.position), get_randomness().next()
    )
    await concept_repository.move_to_domain(session, concept, product.id, x, y)
    await domain_product_repository.bump_revision(session, product)
    product_dto = view.domain_product_dto(product)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "domain_product.changed",
        {
            "domainProduct": product_dto.model_dump(mode="json", by_alias=True),
            "fields": ["revision"],
        },
        company_ids=[company.id],
        bulk=bulk,
    )
    dto = view.concept_dto(concept)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "concept.changed",
        {
            "concept": dto.model_dump(mode="json", by_alias=True),
            "fields": ["domainProductId", "domainKey", "color", "x", "y"],
            "proposalId": str(proposal.id),
        },
        company_ids=[company.id],
        bulk=bulk,
    )
    return DecisionOutcome(artefacts=Artefacts(concepts=[dto], domain_products=[product_dto]))


async def _emit_domain_changed(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    domain: TenantDomain,
    *,
    created: bool,
    bulk: bool,
) -> None:
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        DOMAIN_CHANGED_EVENT,
        {
            "domain": view.domain_dto(domain).model_dump(mode="json", by_alias=True),
            "created": created,
        },
        company_ids=[],
        bulk=bulk,
    )


def _checked_name(name: str | None) -> str:
    if name is None:
        raise validation_failed("payload.name", "name is required")
    problem = domain_name_problem(name)
    if problem is not None:
        raise validation_failed("payload.name", problem)
    return name


def _checked_owner(owner: str | None) -> str:
    owner = owner or ""
    problem = domain_owner_problem(owner)
    if problem is not None:
        raise validation_failed("payload.owner", problem)
    return owner


def _ensure_room(view: OntologyView) -> None:
    if len(view.domains) >= MAX_DOMAINS:
        raise conflict("domain_limit", f"a tenant has at most {MAX_DOMAINS} domains")


def _ensure_name_free(view: OntologyView, name: str, except_key: str | None) -> None:
    """Domain names are unique in the tenant, case-insensitively."""
    for domain in view.domains.values():
        if domain.key != except_key and same_name(domain.name, name):
            raise conflict("duplicate_label", f"a domain called {domain.name} already exists")


def _payload_domain(view: OntologyView, domain_key: str | None) -> TenantDomain:
    if domain_key is None:
        raise validation_failed("payload.domainKey", "domainKey is required")
    domain = view.domains.get(domain_key)
    if domain is None:
        raise not_found("domain")
    return domain


def _payload_concept(view: OntologyView, concept_id: uuid.UUID | None) -> Concept:
    if concept_id is None:
        raise validation_failed("payload.conceptId", "conceptId is required")
    concept = view.concepts.get(concept_id)
    if concept is None or concept.dying_at is not None:
        raise not_found("concept")
    if concept.kind is NodeKind.ROOT:
        raise conflict("root_concept", "the company root belongs to no domain")
    if concept.pending:
        raise conflict("concept_pending", f"{concept.label} is waiting for approval")
    return concept
