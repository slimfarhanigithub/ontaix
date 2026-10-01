"""Whether an organization may add a company: the one rule every company-creating path asks.

`single` company mode turns company creation off once the organization has its one company. An
organization-level setting that turns company creation off can only narrow this rule, so it is
combined into this function and nowhere else.
"""

from __future__ import annotations

from app.models.storage.base import CompanyMode

COMPANY_LIMIT_DETAIL = (
    "This organization has one company only; a super admin sets how many companies it may have"
)


def company_creation_allowed(company_mode: CompanyMode, companies: int) -> bool:
    """False once a `single` organization has its company; always true in `multiple` mode."""
    return not (company_mode is CompanyMode.SINGLE and companies >= 1)
