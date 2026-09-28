"""Relations and equivalences: the Relationships list, single reads and the relation proposals."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ChangeDraft, ChangePayload, RelationDraft
from app.models.api.page import PageOf
from app.models.api.proposal import Proposal as ProposalDto
from app.models.api.relation import Relation as RelationDto
from app.models.api.relation import RelationEdit
from app.models.storage.base import RelationKind
from app.models.storage.relation import Relation
from app.services import proposal_service
from app.services.company_service import readable_companies
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities.listing import ListQuery, matches_search, paginate
from app.utilities.problems import not_found

logger = logging.getLogger(__name__)

FILTERABLE = ("kind", "companyId", "state")
SORTABLE = ("subject", "action", "object", "kind", "state")
KIND_LABELS = {
    RelationKind.REL: "relation",
    RelationKind.ISA: "is a",
    RelationKind.SAME: "equivalence",
    RelationKind.CLASH: "conflict",
}


async def list_relations(
    session: AsyncSession, caller: Caller, query: ListQuery
) -> PageOf[RelationDto]:
    view = await load_view(session, caller.tenant_id)
    rows = [
        (r, view.relation_dto(r))
        for r in _readable_relations(caller, view)
        if _matches(view, r, query)
    ]
    sort_keys = {
        "subject": lambda row: row[1].a_label,
        "action": lambda row: row[1].label,
        "object": lambda row: row[1].b_label,
        "kind": lambda row: KIND_LABELS[row[0].kind],
        "state": lambda row: row[1].state,
    }
    page, total = paginate(rows, query, sort_keys, "subject")
    return PageOf[RelationDto](
        items=[d for _, d in page], page=query.page, page_size=query.page_size, total=total
    )


async def get_relation(
    session: AsyncSession, caller: Caller, relation_id: uuid.UUID
) -> RelationDto:
    view = await load_view(session, caller.tenant_id)
    return view.relation_dto(_readable_relation(caller, view, relation_id))


async def list_equivalences(session: AsyncSession, caller: Caller) -> list[RelationDto]:
    view = await load_view(session, caller.tenant_id)
    return [
        view.relation_dto(r)
        for r in _readable_relations(caller, view)
        if r.kind is RelationKind.SAME
    ]


async def propose_relation(
    session: AsyncSession, caller: Caller, draft: RelationDraft
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    proposal = await proposal_service.create(session, caller, view, draft)
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


async def propose_equivalence(
    session: AsyncSession,
    caller: Caller,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    caption: str | None,
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    proposal = await proposal_service.propose_equivalence(
        session, caller, view, a_id, b_id, caption
    )
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


async def propose_edit(
    session: AsyncSession, caller: Caller, relation_id: uuid.UUID, edit: RelationEdit
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    _readable_relation(caller, view, relation_id)
    draft = ChangeDraft(
        change_kind="edit_relation",
        payload=ChangePayload(relation_id=relation_id, action=edit.action, reverse=edit.reverse),
    )
    proposal = await proposal_service.create(session, caller, view, draft)
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


async def propose_remove(
    session: AsyncSession, caller: Caller, relation_id: uuid.UUID
) -> ProposalDto:
    view = await load_view(session, caller.tenant_id)
    _readable_relation(caller, view, relation_id)
    draft = ChangeDraft(
        change_kind="remove_relation", payload=ChangePayload(relation_id=relation_id)
    )
    proposal = await proposal_service.create(session, caller, view, draft)
    return view.proposal_dto(proposal, view.proposal_artefacts(proposal))


def _readable_relations(caller: Caller, view: OntologyView) -> list[Relation]:
    readable = {c.id for c in readable_companies(caller, view)}
    return [
        r
        for r in view.live_relations()
        if r.a_id in view.concepts
        and r.b_id in view.concepts
        and view.concepts[r.a_id].company_id in readable
        and view.concepts[r.b_id].company_id in readable
    ]


def _readable_relation(caller: Caller, view: OntologyView, relation_id: uuid.UUID) -> Relation:
    relation = view.relations.get(relation_id)
    if relation is None or relation.dying_at is not None:
        raise not_found("relation")
    if relation not in _readable_relations(caller, view):
        raise not_found("relation")
    return relation


def _matches(view: OntologyView, relation: Relation, query: ListQuery) -> bool:
    filters = query.filters
    if "kind" in filters and relation.kind.value not in filters["kind"]:
        return False
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    if "companyId" in filters and not (
        str(a.company_id) in filters["companyId"] or str(b.company_id) in filters["companyId"]
    ):
        return False
    state = "awaiting approval" if relation.pending else "approved"
    if "state" in filters and state not in filters["state"]:
        return False
    return matches_search(
        query.q, a.label, relation.label, b.label, KIND_LABELS[relation.kind], state
    )
