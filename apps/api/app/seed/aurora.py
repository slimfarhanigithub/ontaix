"""Aurora Valves: the acquired company and its nine equivalences to Northwind Industries."""

from __future__ import annotations

COMPANY_NAME = "Aurora Valves"
COMPANY_SUB = "industrial valves · 2 plants · 640 people"

# `(Aurora label, Northwind label)`; each becomes a `same` relation from Aurora to Northwind.
EQUIVALENCES: tuple[tuple[str, str], ...] = (
    ("Site", "Plant"),
    ("Line", "Production line"),
    ("Equipment", "Machine"),
    ("Article", "Product"),
    ("Component", "Material"),
    ("Vendor", "Supplier"),
    ("Client", "Customer"),
    ("Client order", "Sales order"),
    ("Non-conformity", "Defect"),
)

EQUIVALENCE_CAPTION = (
    "{a} at {company_a} is the same concept as {b} at {company_b}. "
    "One meaning, two vocabularies, both kept."
)
