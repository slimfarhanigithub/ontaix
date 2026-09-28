"""Which companies a proposal touches, as recorded on the proposal when it was proposed.

The ids live in `payload.companyIds`, so they survive the rejection or deletion of the rows the
proposal points at. Read access to a proposal, its title and its html is decided from them.
"""

from __future__ import annotations

import uuid

from app.models.storage.proposal import Proposal

PAYLOAD_COMPANY_IDS = "companyIds"


def proposal_company_ids(proposal: Proposal) -> set[uuid.UUID]:
    """The recorded companies; a proposal without them falls back to its own company."""
    recorded = proposal.payload.get(PAYLOAD_COMPANY_IDS) if proposal.payload else None
    if recorded:
        return {uuid.UUID(str(c)) for c in recorded}
    return {proposal.company_id} if proposal.company_id is not None else set()
