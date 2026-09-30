"""Removes approved or pending cells with the relations that touch them, as one dying snapshot."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import concept_repository, relation_repository
from app.services import learning_capture_service, outbox_service
from app.services.ontology_view_service import OntologyView
from app.utilities.clock import get_clock

logger = logging.getLogger(__name__)


async def remove_concepts(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    doomed: list[Concept],
    outcome: DecisionOutcome,
    bulk: bool,
) -> None:
    """Mark the cells dying for the snapshot, then delete them; relations cascade in the DB."""
    doomed = [c for c in doomed if c.id in view.concepts]
    if not doomed:
        return
    now = get_clock().now()
    relation_ids: list[uuid.UUID] = []
    for c in doomed:
        await concept_repository.mark_dying(session, c, now)
        for r in view.relations_touching(c.id):
            if r.id not in relation_ids:
                relation_ids.append(r.id)
                await relation_repository.mark_dying(session, r, now)
    outcome.artefacts.concepts = [view.concept_dto(c) for c in doomed]
    outcome.artefacts.relations = [view.relation_dto(view.relations[r]) for r in relation_ids]
    for c in doomed:
        await concept_repository.delete(session, c)
        view.forget_concept(c.id)
    await learning_capture_service.on_concepts_removed(session, caller, view, doomed)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        "concept.dying",
        {
            "conceptIds": [str(c.id) for c in doomed],
            "relationIds": [str(r) for r in relation_ids],
            "bindingIds": [],
            "proposalId": str(proposal.id),
        },
        company_ids={c.company_id for c in doomed},
        bulk=bulk,
    )
