"""The thirteen-concept starter vocabulary proposed for a company that starts with its own words.

Rows are `(label, domain key, action, parent label)`; a `None` parent means the company root.
"""

from __future__ import annotations

STARTER_VOCABULARY: tuple[tuple[str, str, str, str | None], ...] = (
    ("Site", "production", "operates", None),
    ("Line", "production", "runs", "Site"),
    ("Equipment", "production", "has", "Line"),
    ("Article", "production", "produces", "Line"),
    ("Component", "supply", "uses", "Article"),
    ("Vendor", "supply", "bought from", "Component"),
    ("Purchase requisition", "supply", "requested by", "Component"),
    ("Client", "sales", "serves", None),
    ("Client order", "sales", "places", "Client"),
    ("Non-conformity", "quality", "raises", "Article"),
    ("Field service", "maintenance", "serviced by", "Equipment"),
    ("Staff member", "people", "employs", None),
    ("Ledger entry", "finance", "posted by", "Client order"),
)
