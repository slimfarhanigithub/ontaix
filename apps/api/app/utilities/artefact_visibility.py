"""The one rule for artefacts in a response: a caller only receives rows of companies it reads.

Every response that carries artefacts (decision results, proposals in lists, the scene and the
creation answers) passes them through `readable_proposal` or `readable_artefacts`. A relation is
kept only when every company it joins is readable, so another company's labels never reach a
caller that cannot read that company. The client never drew a row it cannot read, so dropping
the row loses nothing on the canvas.

Outbox events keep the full data. `event_company_id` scopes an event to its single company, or
to no company when it touches several, since an outbox row names at most one company.
"""

from __future__ import annotations

import uuid

from app.models.api.proposal import Artefacts
from app.models.api.proposal import Proposal as ProposalDto
from app.utilities.permissions import Grant, can_read


def artefact_company_ids(artefacts: Artefacts) -> set[uuid.UUID]:
    """Every company whose rows appear in the artefacts."""
    ids: set[uuid.UUID] = {c.company_id for c in artefacts.concepts}
    for relation in artefacts.relations:
        ids.update(relation.company_ids)
    ids.update(p.company_id for p in artefacts.domain_products)
    ids.update(uuid.UUID(str(c["id"])) for c in artefacts.companies if c.get("id"))
    return ids


def readable_artefacts(grants: tuple[Grant, ...], artefacts: Artefacts) -> Artefacts:
    """The artefacts without any row of a company the caller may not read."""
    return artefacts.model_copy(
        update={
            "concepts": [c for c in artefacts.concepts if can_read(grants, c.company_id)],
            "relations": [
                r
                for r in artefacts.relations
                if all(can_read(grants, company_id) for company_id in r.company_ids)
            ],
            "domain_products": [
                p for p in artefacts.domain_products if can_read(grants, p.company_id)
            ],
            "companies": [
                c
                for c in artefacts.companies
                if not c.get("id") or can_read(grants, uuid.UUID(str(c["id"])))
            ],
        }
    )


def readable_proposal(grants: tuple[Grant, ...], proposal: ProposalDto) -> ProposalDto:
    """The proposal with its artefacts filtered by `readable_artefacts`."""
    if proposal.artefacts is None:
        return proposal
    return proposal.model_copy(update={"artefacts": readable_artefacts(grants, proposal.artefacts)})


def event_company_id(company_ids: set[uuid.UUID]) -> uuid.UUID | None:
    """The company an event is limited to: its only company, otherwise none."""
    return next(iter(company_ids)) if len(company_ids) == 1 else None
