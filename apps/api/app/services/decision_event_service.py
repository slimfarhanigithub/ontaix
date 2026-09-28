"""The outbox events of decisions: one per decided proposal and one per bulk run.

A proposal event's audience is every company the proposal touches plus every company of the
artefacts it carries. Its `cascaded` list keeps only the cascaded proposals whose companies are
all in that audience; every cascaded proposal also has its own `proposal.rejected` event with
its own audience, so a reader of fewer companies still learns about it.
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
from app.utilities.artefact_visibility import artefact_company_ids
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
    cascaded = [
        c for c in outcome.cascaded if outcome.cascaded_company_ids.get(c.id, set()) <= companies
    ]
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        event_type,
        {
            "proposal": dto.model_dump(mode="json", by_alias=True, exclude={"artefacts"}),
            "artefacts": outcome.artefacts.model_dump(mode="json", by_alias=True),
            "cascaded": [
                c.model_dump(mode="json", by_alias=True, exclude={"artefacts"}) for c in cascaded
            ],
            "caption": outcome.caption,
        },
        company_ids=companies,
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
