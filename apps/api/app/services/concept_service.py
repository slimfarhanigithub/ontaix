"""Concepts: the Entities list, single reads, lineage, attributes, rename and delete proposals."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.attribute import Attribute as AttributeDto
from app.models.api.concept import Concept as ConceptDto
from app.models.api.drafts import ChangeDraft, ChangePayload, ConceptDraft, SpecDraft
from app.models.api.lineage import Lineage, LineageNode, LineageStep
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.base import NodeKind
from app.models.storage.concept import Concept
from app.services import proposal_service
from app.services.company_service import readable_companies
from app.services.ontology_view_service import OntologyView, attribute_dto, load_view
from app.services.proposal_store_service import ISA_ACTION
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.listing import ListQuery, matches_search, paginate
from app.utilities.permissions import can_read
from app.utilities.problems import forbidden, not_found

logger = logging.getLogger(__name__)

FILTERABLE = ("companyId", "domainKey", "state", "kind", "bound")
SORTABLE = ("label", "company", "domain", "state", "relations", "bornAt")


async def list_concepts(
    session: AsyncSession, caller: Caller, query: ListQuery
) -> PageOf[ConceptDto]:
    view = await load_view(session, caller.tenant_id)
    readable = {c.id for c in readable_companies(caller, view)}
    rows = [
        (c, view.concept_dto(c))
        for c in view.live_concepts()
        if c.company_id in readable and c.kind is NodeKind.CONCEPT
    ]
    rows = [(c, d) for c, d in rows if _matches(view, c, d, query)]
    company_name = {c.id: c.name for c in view.companies.values()}
    sort_keys = {
        "label": lambda r: r[1].label,
        "company": lambda r: company_name.get(r[0].company_id, ""),
        "domain": lambda r: view.domain_name(r[0]) or "",
        "state": lambda r: r[1].state,
        "relations": lambda r: r[1].relation_count,
        "bornAt": lambda r: r[0].born_at,
    }
    page, total = paginate(rows, query, sort_keys, "label")
    return PageOf[ConceptDto](
        items=[d for _, d in page], page=query.page, page_size=query.page_size, total=total
    )


async def get_concept(session: AsyncSession, caller: Caller, concept_id: uuid.UUID) -> ConceptDto:
    view = await load_view(session, caller.tenant_id)
    return view.concept_dto(_readable_concept(caller, view, concept_id))


async def list_attributes(
    session: AsyncSession, caller: Caller, concept_id: uuid.UUID
) -> list[AttributeDto]:
    view = await load_view(session, caller.tenant_id)
    concept = _readable_concept(caller, view, concept_id)
    return [attribute_dto(a) for a in view.attributes.get(concept.id, [])]


async def get_lineage(session: AsyncSession, caller: Caller, concept_id: uuid.UUID) -> Lineage:
    view = await load_view(session, caller.tenant_id)
    concept = _readable_concept(caller, view, concept_id)
    ancestors = view.ancestors_of(concept.id)
    descendants = view.descendants_of(concept.id)
    chain = " → ".join(a.label for a in ancestors)
    caption = (f"{chain} → " if ancestors else "") + concept.label
    if descendants:
        plural = "" if len(descendants) == 1 else "s"
        caption += f" → {len(descendants)} descendant{plural}"
    caption += ". Everything else is dimmed."
    return Lineage(
        concept=view.concept_dto(concept),
        ancestors=[_step(view, a) for a in ancestors],
        descendants=[_node(view, k) for k in view.children_of(concept.id)],
        data_lineage=[],
        set_ids=[concept.id, *(a.id for a in ancestors), *(d.id for d in descendants)],
        caption=caption,
    )


async def propose_concept(
    session: AsyncSession, caller: Caller, draft: ConceptDraft | SpecDraft
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


async def propose_rename(
    session: AsyncSession, caller: Caller, concept_id: uuid.UUID, label: str
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    _readable_concept(caller, view, concept_id)
    draft = ChangeDraft(
        change_kind="rename", payload=ChangePayload(concept_id=concept_id, new_label=label)
    )
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


async def propose_delete(
    session: AsyncSession, caller: Caller, concept_id: uuid.UUID
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    _readable_concept(caller, view, concept_id)
    draft = ChangeDraft(change_kind="delete_concept", payload=ChangePayload(concept_id=concept_id))
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


def _readable_concept(caller: Caller, view: OntologyView, concept_id: uuid.UUID) -> Concept:
    concept = view.concepts.get(concept_id)
    if concept is None or concept.dying_at is not None:
        raise not_found("concept")
    if not can_read(caller.grants, concept.company_id):
        raise forbidden("you may not read this company")
    return concept


def _matches(view: OntologyView, concept: Concept, dto: ConceptDto, query: ListQuery) -> bool:
    filters: Mapping[str, list[str]] = query.filters
    if "companyId" in filters and str(concept.company_id) not in filters["companyId"]:
        return False
    if "domainKey" in filters and (view.domain_key(concept) or "") not in filters["domainKey"]:
        return False
    if "state" in filters and dto.state not in filters["state"]:
        return False
    if "kind" in filters:
        kind = "specialisation" if dto.is_specialisation else "concept"
        if kind not in filters["kind"]:
            return False
    if "bound" in filters and "false" not in [v.lower() for v in filters["bound"]]:
        return False
    company = view.companies.get(concept.company_id)
    return matches_search(
        query.q,
        concept.label,
        company.name if company else None,
        view.domain_name(concept),
        "specialisation" if dto.is_specialisation else "concept",
    )


def _how(view: OntologyView, concept: Concept) -> str:
    if concept.kind is NodeKind.ROOT:
        return "the company"
    parent = view.concepts.get(concept.parent_id) if concept.parent_id else None
    if parent is None or not concept.birth_action:
        return ""
    if concept.birth_action == ISA_ACTION:
        return f"is a {parent.label}"
    if concept.birth_reverse:
        return f"{concept.label} {concept.birth_action} {parent.label}"
    return f"{parent.label} {concept.birth_action} {concept.label}"


def _step(view: OntologyView, concept: Concept) -> LineageStep:
    return LineageStep(
        concept_id=concept.id,
        label=concept.label,
        how=_how(view, concept),
        domain_name=view.domain_name(concept),
        pending=concept.pending,
        born_at=concept.born_at,
    )


def _node(view: OntologyView, concept: Concept) -> LineageNode:
    return LineageNode(
        concept_id=concept.id,
        label=concept.label,
        how=_how(view, concept),
        pending=concept.pending,
        below=len(view.descendants_of(concept.id)),
        children=[_node(view, k) for k in view.children_of(concept.id)],
    )
