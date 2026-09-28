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
from app.models.storage.base import ActorKind, ChangeKind, ProposalType
from app.models.storage.proposal import Proposal
from app.repositories import proposal_repository
from app.services import outbox_service
from app.services.ontology_view_service import OntologyView
from app.utilities.permissions import Scope, can_propose
from app.utilities.problems import forbidden

logger = logging.getLogger(__name__)

ISA_ACTION = "is a"
SAME_ACTION = "equivalent to"


def esc(value: str) -> str:
    """HTML-escape a label before it enters the panel markup."""
    return html.escape(value, quote=True)


def ensure_can_propose(caller: Caller, scope: Scope) -> None:
    if not can_propose(caller.grants, scope, caller.everyone_teaches):
        raise forbidden("your roles do not allow proposing in this scope")


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
    concept_id: uuid.UUID | None,
    relation_id: uuid.UUID | None,
    bulk: bool,
) -> Proposal:
    """Write the proposal row and its `proposal.created` event."""
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
