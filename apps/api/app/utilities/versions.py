"""Display form of a domain product revision."""

from __future__ import annotations


def version_label(revision: int) -> str:
    """Render an integer revision as `v1.<revision>`."""
    return f"v1.{revision}"
