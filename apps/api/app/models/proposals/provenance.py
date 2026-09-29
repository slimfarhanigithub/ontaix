"""The provenance a new proposal is stored with: its origin and, for a document, the detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.storage.base import ProposalOrigin


@dataclass(frozen=True)
class Provenance:
    """`detail` is the `originDetail` object, set exactly when `origin` is `document`."""

    origin: ProposalOrigin = ProposalOrigin.TEXT
    detail: dict[str, Any] | None = None


TYPED_TEXT = Provenance()
