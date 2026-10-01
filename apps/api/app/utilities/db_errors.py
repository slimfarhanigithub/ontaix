"""Reads which constraint a database error names."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError


def constraint_name(exc: BaseException) -> str | None:
    """The constraint a PostgreSQL error reports, including the names the company-mode
    triggers raise (`company_limit`, `locked_setting`); None for anything else."""
    if not isinstance(exc, DBAPIError):
        return None
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
