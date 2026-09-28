"""The outbox events of decisions: one per decided proposal and one per bulk run.

A proposal event keeps its full payload. It is limited to one company only when everything it
carries belongs to that company; an event that spans several companies names none, because an
outbox row can name at most one.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import BulkResult
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import NodeKind, RelationKind
from app.models.storage.proposal import Proposal
from app.services import outbox_service
from app.services.ontology_view_service import OntologyView
from app.utilities.artefact_visibility import artefact_company_ids, event_company_id
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)


async def emit_proposal_event(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    event_type: str,
    outcome: DecisionOutcome,
    bulk: bool,
) -> None:
    dto = view.proposal_dto(proposal)
    companies = proposal_company_ids(proposal) | artefact_company_ids(outcome.artefacts)
    spans_tenant = False
    for cascaded in outcome.cascaded:
        if cascaded.company_id is None:
            spans_tenant = True
        else:
            companies.add(cascaded.company_id)
        if cascaded.artefacts is not None:
            companies |= artefact_company_ids(cascaded.artefacts)
    company_id = None if spans_tenant else event_company_id(companies)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        event_type,
        {
            "proposal": dto.model_dump(mode="json", by_alias=True, exclude={"artefacts"}),
            "artefacts": outcome.artefacts.model_dump(mode="json", by_alias=True),
            "cascaded": [
                c.model_dump(mode="json", by_alias=True, exclude={"artefacts"})
                for c in outcome.cascaded
            ],
            "caption": outcome.caption,
        },
        company_id=company_id if company_id in view.companies else None,
        bulk=bulk,
    )


async def emit_finalised(
    session: AsyncSession, caller: Caller, view: OntologyView, result: BulkResult
) -> None:
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "proposal.finalised",
        {
            "approved": result.approved,
            "rejected": result.rejected,
            "rounds": result.rounds,
            "remaining": result.remaining,
            "companies": len(view.companies),
            "concepts": sum(1 for c in view.live_concepts() if c.kind is NodeKind.CONCEPT),
            "bound": 0,
            "equivalences": sum(1 for r in view.live_relations() if r.kind is RelationKind.SAME),
            "caption": result.caption,
        },
        bulk=True,
    )
