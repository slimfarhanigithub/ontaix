"""`POST /expansions/{expansionId}/proposals`: a selection of stored suggestions to proposals.

The expansion belongs to the user that made it, in its tenant; the selection must be closed
under `requires`, and the caller must still hold `proposal.create` through Owner or Builder in
the expanded concept's scope. The expansion is claimed once with a conditional update inside the
request's transaction, so a refused draft rolls the claim back with everything else. Each
proposal records origin `suggestion` and the suggestion's confidence and rationale as its `why`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.expansion import ExpansionSelection
from app.models.api.proposal import Proposal as ProposalDto
from app.models.proposals.provenance import Provenance
from app.models.storage.base import ProposalOrigin
from app.repositories import concept_expansion_repository
from app.services import learning_capture_service, stored_draft_service, teach_session_service
from app.services.concept_expansion_service import expansion_scope
from app.services.ontology_view_service import load_view
from app.services.rate_limit_service import charge_proposals
from app.services.teach_draft_service import new_labels
from app.utilities.permissions import can_propose_as_builder, can_read
from app.utilities.problems import ProblemError, conflict, forbidden, not_found

logger = logging.getLogger(__name__)

SUGGESTED_WHY = "Suggested by the model · {percent}% · {rationale}"


async def propose(
    session: AsyncSession, caller: Caller, expansion_id: uuid.UUID, body: ExpansionSelection
) -> list[ProposalDto]:
    row = await concept_expansion_repository.get(session, caller.tenant_id, expansion_id)
    if row is None or row.actor_user_id != caller.user_id:
        raise not_found("expansion")
    view = await load_view(session, caller.tenant_id)
    concept = view.concepts.get(row.concept_id)
    if (
        concept is None
        or concept.dying_at is not None
        or not can_read(caller.grants, concept.company_id)
    ):
        raise not_found("expansion")
    if not can_propose_as_builder(caller.grants, expansion_scope(view, concept)):
        raise forbidden("Proposing suggestions needs the Owner or Builder role in this scope")
    if not await concept_expansion_repository.claim_submit(session, caller.tenant_id, row.id):
        await session.refresh(row)
        if row.submitted_at is not None:
            raise conflict("expansion_submitted", "these suggestions were proposed already")
        raise ProblemError(410, "expansion_expired", "the suggestions have expired; expand again")
    indexes = stored_draft_service.selected(body.indexes, row.notes)
    await charge_proposals(caller, len(indexes))
    drafts = [row.drafts[i] for i in indexes]
    provenances = [Provenance(ProposalOrigin.SUGGESTION, None, _why(row.notes[i])) for i in indexes]
    created = await stored_draft_service.propose(session, caller, view, drafts, provenances)
    await learning_capture_service.link_stored(
        session,
        caller.tenant_id,
        view.companies[concept.company_id],
        learning_capture_service.KIND_EXPAND,
        row.id,
        indexes,
        [p.id for p in created],
    )
    await session.commit()
    if row.session_id is not None:
        key = teach_session_service.session_key(caller, concept.company_id, row.session_id)
        await teach_session_service.store_turn(
            key, f"Expand {concept.label}", "llm", [concept.id], new_labels(drafts)
        )
    return created


def _why(note: dict) -> str:
    percent = round(float(note["confidence"]) * 100)
    return SUGGESTED_WHY.format(percent=percent, rationale=note["rationale"])
