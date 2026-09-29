"""Proposals built from drafts the server stored itself: a concept expansion or a whole-document
extraction result. The client sends indexes only, so what is proposed is exactly what the server
validated; each draft still meets every check of `POST /proposals/batch`."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ProposalDraft
from app.models.api.proposal import Proposal as ProposalDto
from app.models.proposals.provenance import Provenance
from app.services import proposal_service
from app.services.ontology_view_service import OntologyView
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.draft_selection import selection_problem
from app.utilities.problems import validation_failed

logger = logging.getLogger(__name__)

_DRAFT = TypeAdapter(ProposalDraft)


def selected(indexes: list[int], notes: list[dict[str, Any]]) -> list[int]:
    """The selection in draft order, or `422` when it is out of range or not closed under
    `requires`."""
    problem = selection_problem(indexes, notes)
    if problem:
        raise validation_failed("indexes", problem)
    return sorted(indexes)


async def propose(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    drafts: list[dict[str, Any]],
    provenances: list[Provenance],
) -> list[ProposalDto]:
    """Create one proposal per stored draft, in order, in the caller's transaction."""
    parsed = [_DRAFT.validate_python(d) for d in drafts]
    created = await proposal_service.create_batch(session, caller, view, parsed, provenances)
    return [
        readable_proposal(caller.grants, view.proposal_dto(p, view.proposal_artefacts(p)))
        for p in created
    ]
