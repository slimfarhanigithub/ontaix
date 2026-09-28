"""The audience of an outbox event or an audit entry: every company it names.

An empty audience is tenant-wide. A reader receives the row only when it holds the row's
visibility permission in a scope that contains every listed company.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable


def audience(*groups: Iterable[uuid.UUID | None]) -> list[uuid.UUID]:
    """The distinct companies of every group, in a stable order; `None` entries are skipped."""
    return sorted({c for group in groups for c in group if c is not None}, key=str)
