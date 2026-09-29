"""The provenance each new proposal records, and the channel gates on the way in.

`text` and `speech` are what the client declares; `document` is recorded only for a draft that
cites a stored import sentence, with the detail read from the stored import. The generic
proposal endpoints claim each cited sentence once per call: several drafts of one call may cite
the same sentence, a later call may not.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ProposalBatch
from app.models.proposals.provenance import Provenance
from app.models.storage.base import ProposalOrigin
from app.services import import_service
from app.services.ontology_view_service import OntologyView
from app.utilities.channels import ensure_import_allowed, ensure_speech_allowed
from app.utilities.problems import validation_failed

logger = logging.getLogger(__name__)


def declared(view: OntologyView, draft) -> Provenance:
    """The provenance of a draft sent to a resource endpoint, which refuses import references."""
    if draft.import_ref is not None:
        raise validation_failed(
            "importRef", "an import reference is accepted by the generic proposal endpoints only"
        )
    return _declared_origin(view, draft.origin)


def with_batch_defaults(batch: ProposalBatch) -> list:
    """The batch's drafts, each carrying the batch-level origin and import reference unless it
    sets its own."""
    drafts = []
    for draft in batch.drafts:
        update = {}
        if draft.origin is None and batch.origin is not None:
            update["origin"] = batch.origin
        if draft.import_ref is None and batch.import_ref is not None:
            update["import_ref"] = batch.import_ref
        drafts.append(draft.model_copy(update=update) if update else draft)
    return drafts


async def resolve(
    session: AsyncSession, caller: Caller, view: OntologyView, drafts: list
) -> list[Provenance]:
    """One provenance per draft, in order; checks every gate before claiming any sentence."""
    for draft in drafts:
        if draft.import_ref is not None:
            ensure_import_allowed(view.settings)
        elif draft.origin == "speech":
            ensure_speech_allowed(view.settings)
    claimed: dict[tuple[uuid.UUID, int], Provenance] = {}
    for draft in drafts:
        ref = draft.import_ref
        if ref is None or (ref.import_id, ref.sentence_index) in claimed:
            continue
        row = await import_service.owned_import(session, caller, ref.import_id)
        sentence = await import_service.claim_draft(session, caller, row, ref.sentence_index)
        claimed[(ref.import_id, ref.sentence_index)] = Provenance(
            ProposalOrigin.DOCUMENT,
            import_service.origin_detail(row, ref.sentence_index, sentence),
        )
    return [
        claimed[(d.import_ref.import_id, d.import_ref.sentence_index)]
        if d.import_ref is not None
        else _declared_origin(view, d.origin)
        for d in drafts
    ]


def _declared_origin(view: OntologyView, origin: str | None) -> Provenance:
    if origin == "speech":
        ensure_speech_allowed(view.settings)
        return Provenance(ProposalOrigin.SPEECH)
    return Provenance(ProposalOrigin.TEXT)
