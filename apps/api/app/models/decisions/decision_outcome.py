"""What one decision produced: the artefacts it changed, the cascade, the caption and the audit."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.api.audit import AuditEntry
from app.models.api.proposal import Artefacts
from app.models.api.proposal import Proposal as ProposalDto


@dataclass
class DecisionOutcome:
    artefacts: Artefacts
    cascaded: list[ProposalDto] = field(default_factory=list)
    caption: str | None = None
    audit: AuditEntry | None = None
