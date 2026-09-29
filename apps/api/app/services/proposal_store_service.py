"""Shared by every proposal builder: the proposal row with its event, the propose check, escaping.

Panel `html` is built by the builders only: every label passes through `esc` and the markup
uses `<b>` and `<i>` alone.
"""

from __future__ import annotations

import html
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.proposals.provenance import TYPED_TEXT, Provenance
from app.models.storage.base import ActorKind, ChangeKind, ProposalType
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.repositories import (
    company_repository,
    concept_repository,
    proposal_repository,
    relation_repository,
)
from app.services import outbox_service
from app.services.ontology_view_service import OntologyView
from app.utilities.artefact_visibility import artefact_company_ids
from app.utilities.permissions import Scope, can_propose
from app.utilities.problems import conflict, forbidden
from app.utilities.proposal_scope import PAYLOAD_COMPANY_IDS

logger = logging.getLogger(__name__)

ISA_ACTION = "is a"
SAME_ACTION = "equivalent to"


def esc(value: str) -> str:
    """HTML-escape a label before it enters the panel markup."""
    return html.escape(value, quote=True)


async def ensure_still_live(session: AsyncSession, view: OntologyView, concept: Concept) -> None:
    """Re-check under the tenant decision lock that a concept read from the view still exists.

    A proposal that depends on a pending concept must not be written after that concept's
    proposal was rejected: its dependency could never resolve.
    """
    if not await concept_repository.exists(session, view.tenant_id, concept.id):
        raise conflict(
            "proposal_decided",
            f"{concept.label} was rejected or removed while this proposal was being created",
        )


async def ensure_relation_still_live(
    session: AsyncSession, view: OntologyView, relation: Relation
) -> None:
    """Re-check under the tenant decision lock that a relation read from the view still exists."""
    if not await relation_repository.exists(session, view.tenant_id, relation.id):
        raise conflict(
            "proposal_decided", "the relation was removed while this proposal was being created"
        )


async def ensure_company_still_live(
    session: AsyncSession, view: OntologyView, company: Company
) -> None:
    """Re-check under the tenant decision lock that a company read from the view still exists."""
    if not await company_repository.exists(session, view.tenant_id, company.id):
        raise conflict(
            "proposal_decided", f"{company.name} was removed while this proposal was being created"
        )


async def ensure_label_free(
    session: AsyncSession, view: OntologyView, company_id: uuid.UUID, label: str
) -> None:
    """Check label uniqueness in the company against the database, under the decision lock."""
    if await concept_repository.label_taken(session, view.tenant_id, company_id, label):
        raise conflict("duplicate_label", f"{label} already exists in this company")


def ensure_can_propose(caller: Caller, scope: Scope) -> None:
    if not can_propose(caller.grants, scope, caller.everyone_teaches):
        raise forbidden("Your roles do not allow proposing in this scope")


async def store(
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
    touched_company_ids: list[uuid.UUID],
    concept_id: uuid.UUID | None,
    relation_id: uuid.UUID | None,
    bulk: bool,
    provenance: Provenance = TYPED_TEXT,
    attribute_id: uuid.UUID | None = None,
) -> Proposal:
    """Write the proposal row and its `proposal.created` event.

    `touched_company_ids` is recorded in `payload.companyIds`: read access to the proposal is
    decided from it, also after the rows it points at are gone. `provenance` is the origin the
    proposal records, with the document detail when it cites an import.
    """
    unique_ids = list(dict.fromkeys(touched_company_ids))
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
        payload={**payload, PAYLOAD_COMPANY_IDS: [str(c) for c in unique_ids]},
        concept_id=concept_id,
        relation_id=relation_id,
        relation_ids=[],
        attribute_id=attribute_id,
        proposer_kind=ActorKind(proposer.kind),
        proposer_user_id=proposer.id if proposer.kind == "user" else None,
        bulk=bulk,
        origin=provenance.origin,
        origin_detail=provenance.detail,
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
        company_ids=unique_ids
        + (list(artefact_company_ids(dto.artefacts)) if dto.artefacts else []),
        bulk=bulk,
    )
    return proposal
