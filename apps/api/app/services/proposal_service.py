"""Creates proposals from typed drafts and writes their pending artefacts at once.

Every ontology mutation endpoint ends here. Creating a proposal writes the pending concept and
its birth relation, or the pending relation, in the same transaction as the proposal row, the
`proposal.created` event and the `concept.born` or `relation.created` event. Nothing here ever
writes an approved row.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.actor import Actor
from app.models.api.drafts import (
    AttributeDraft,
    BindingDraft,
    ChangeDraft,
    ConceptDraft,
    RelationDraft,
    SourceDraft,
    SpecDraft,
)
from app.models.proposals.provenance import Provenance
from app.models.storage.proposal import Proposal
from app.services import decision_lock_service, provenance_service
from app.services.change_proposal_service import propose_change
from app.services.concept_proposal_service import propose_concept, propose_spec
from app.services.ontology_view_service import OntologyView
from app.services.proposal_store_service import SAME_ACTION
from app.services.relation_proposal_service import propose_relation
from app.utilities.problems import ProblemError, conflict, not_found

logger = logging.getLogger(__name__)

Draft = (
    ConceptDraft
    | SpecDraft
    | RelationDraft
    | SourceDraft
    | BindingDraft
    | AttributeDraft
    | ChangeDraft
)


async def create(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    draft: Draft,
    *,
    bulk: bool = False,
    enforce_permission: bool = True,
    proposer: Actor | None = None,
    provenance: Provenance | None = None,
) -> Proposal:
    """Create one proposal with its pending artefacts; refusals are Problem+JSON errors.

    `proposer` defaults to the caller; the starter vocabulary passes the system actor. The
    tenant decision lock is taken first, so a proposal and a decision never interleave.
    `provenance` is resolved by the generic endpoints, which accept import references; when it
    is None the draft's declared origin is used and an import reference is refused.
    """
    prov = provenance or provenance_service.declared(view, draft)
    await decision_lock_service.acquire(session, view.tenant_id)
    who = proposer or caller.actor
    enforce = enforce_permission
    match draft:
        case ConceptDraft():
            return await propose_concept(session, caller, who, view, draft, bulk, enforce, prov)
        case SpecDraft():
            return await propose_spec(session, caller, who, view, draft, bulk, enforce, prov)
        case RelationDraft():
            return await propose_relation(session, caller, who, view, draft, bulk, enforce, prov)
        case ChangeDraft():
            return await propose_change(session, caller, who, view, draft, bulk, enforce, prov)
        case _:
            raise ProblemError(
                503, "unavailable", f"{draft.type} proposals are served by the bindings module"
            )


async def create_batch(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    drafts: list[Draft],
    provenances: list[Provenance],
) -> list[Proposal]:
    """Create drafts in order so later ones may name labels introduced by earlier ones."""
    return [
        await create(session, caller, view, draft, provenance=provenance)
        for draft, provenance in zip(drafts, provenances, strict=True)
    ]


async def propose_equivalence(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    caption: str | None,
) -> Proposal:
    """A `same` relation between two companies' concepts."""
    a, b = view.concepts.get(a_id), view.concepts.get(b_id)
    if a is None or b is None:
        raise not_found("concept")
    if a.company_id == b.company_id:
        raise conflict("same_company", "both concepts belong to one company")
    draft = RelationDraft(a_id=a_id, b_id=b_id, action=SAME_ACTION, caption=caption)
    await decision_lock_service.acquire(session, view.tenant_id)
    return await propose_relation(session, caller, caller.actor, view, draft, False, True)
