"""What one decision produced: the artefacts it changed, the cascade, the caption and the audit."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.models.api.audit import AuditEntry
from app.models.api.proposal import Artefacts
from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.company import Company


@dataclass
class DecisionOutcome:
    """`cascaded_company_ids` maps each cascaded proposal to the companies it touches.

    `removed_company` is a company the decision removes: it is marked dying and its row is
    deleted only after the decision's audit entry and events, which still name it, are written.
    """

    artefacts: Artefacts
    cascaded: list[ProposalDto] = field(default_factory=list)
    cascaded_company_ids: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    caption: str | None = None
    audit: AuditEntry | None = None
    removed_company: Company | None = None

    def add_cascaded(self, proposal: ProposalDto, company_ids: set[uuid.UUID]) -> None:
        self.cascaded.append(proposal)
        self.cascaded_company_ids[proposal.id] = company_ids

    def absorb_cascade(self, other: DecisionOutcome) -> None:
        """Take over the proposals `other` rejected in its own cascade."""
        self.cascaded.extend(other.cascaded)
        self.cascaded_company_ids.update(other.cascaded_company_ids)
