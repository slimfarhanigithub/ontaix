"""Northwind Industries: the dev and test fixture's home company and its concepts.

Each batch lists the proposals of one domain product in order; a batch is proposed, then
approved, before the next one. A `concept` row is `(parent label, label, domain key,
action, caption)`; a `spec` row is `(parent label, label, rule, caption, domain key)`; a
`relation` row is `(subject label, action, object label, caption)`.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPANY_NAME = "Northwind Industries"
COMPANY_SUB = "industrial pumps · 4 plants · 2,300 people"


@dataclass(frozen=True)
class ConceptRow:
    parent: str
    label: str
    domain: str
    action: str
    caption: str


@dataclass(frozen=True)
class SpecRow:
    parent: str
    label: str
    rule: str
    caption: str
    domain: str


@dataclass(frozen=True)
class RelationRow:
    subject: str
    action: str
    object: str
    caption: str


@dataclass(frozen=True)
class Batch:
    name: str
    rows: tuple[ConceptRow | SpecRow | RelationRow, ...]


BATCHES: tuple[Batch, ...] = (
    Batch(
        "Production",
        (
            ConceptRow(
                COMPANY_NAME, "Plant", "production", "operates", "Plant is kept in Production."
            ),
            ConceptRow(
                "Plant", "Production line", "production", "runs", "Production line is kept."
            ),
            ConceptRow("Production line", "Machine", "production", "has", "Machine is kept."),
            ConceptRow("Production line", "Shift", "production", "runs in", "Shift is kept."),
            ConceptRow("Shift", "Operator", "production", "staffed by", "Operator is kept."),
            ConceptRow(
                "Production line", "Work order", "production", "executes", "Work order is kept."
            ),
            ConceptRow(
                "Work order",
                "Product",
                "production",
                "produces",
                "Product is kept. Production is now a product of its own: owned, versioned, consumable.",
            ),
        ),
    ),
    Batch(
        "Supply chain",
        (
            ConceptRow(
                "Product",
                "Bill of materials",
                "supply",
                "defined by",
                "Bill of materials is kept in Supply chain. Product is defined by it: a relation across two domain products.",
            ),
            ConceptRow("Bill of materials", "Material", "supply", "lists", "Material is kept."),
            ConceptRow("Material", "Supplier", "supply", "bought from", "Supplier is kept."),
            ConceptRow(
                "Supplier", "Purchase order", "supply", "receives", "Purchase order is kept."
            ),
            ConceptRow("Material", "Warehouse", "supply", "stored in", "Warehouse is kept."),
            ConceptRow("Warehouse", "Stock level", "supply", "tracks", "Stock level is kept."),
        ),
    ),
    Batch(
        "Sales",
        (
            ConceptRow(COMPANY_NAME, "Customer", "sales", "serves", "Customer is kept in Sales."),
            ConceptRow("Customer", "Sales region", "sales", "grouped in", "Sales region is kept."),
            ConceptRow("Customer", "Quotation", "sales", "requests", "Quotation is kept."),
            ConceptRow("Quotation", "Sales order", "sales", "becomes", "Sales order is kept."),
            ConceptRow("Sales order", "Price list", "sales", "priced from", "Price list is kept."),
            RelationRow(
                "Sales order",
                "contains",
                "Product",
                "Sales order contains Product: Sales reads Production’s definition of Product rather than inventing its own.",
            ),
            RelationRow(
                "Sales order",
                "triggers",
                "Work order",
                "Sales order triggers Work order: the hand-over between the two domain products is explicit.",
            ),
        ),
    ),
    Batch(
        "Logistics",
        (
            ConceptRow(
                "Sales order",
                "Delivery",
                "logistics",
                "fulfilled by",
                "Delivery is kept in Logistics.",
            ),
            ConceptRow("Delivery", "Shipment", "logistics", "packed as", "Shipment is kept."),
            ConceptRow("Shipment", "Carrier", "logistics", "handled by", "Carrier is kept."),
            ConceptRow("Shipment", "Route", "logistics", "follows", "Route is kept."),
            RelationRow(
                "Shipment",
                "leaves from",
                "Warehouse",
                "Shipment leaves from Warehouse: Logistics reads Supply chain’s Warehouse.",
            ),
        ),
    ),
    Batch(
        "Quality and maintenance",
        (
            ConceptRow(
                "Product", "Inspection", "quality", "checked by", "Inspection is kept in Quality."
            ),
            ConceptRow(
                "Inspection",
                "Quality standard",
                "quality",
                "complies with",
                "Quality standard is kept.",
            ),
            ConceptRow("Inspection", "Defect", "quality", "records", "Defect is kept."),
            SpecRow(
                "Machine",
                "Machine due for maintenance",
                "> 5,000 h since last service",
                "Machine divides across the boundary: Maintenance owns the specialisation, Production still owns Machine, and the dashed “is a” keeps the two tied.",
                "maintenance",
            ),
            ConceptRow(
                "Machine due for maintenance",
                "Maintenance plan",
                "maintenance",
                "scheduled by",
                "Maintenance plan is kept.",
            ),
            ConceptRow(
                "Maintenance plan", "Spare part", "maintenance", "needs", "Spare part is kept."
            ),
            ConceptRow(
                "Machine",
                "Sensor",
                "maintenance",
                "monitored by",
                "Sensor is kept in Maintenance, attached to Production’s Machine.",
            ),
        ),
    ),
    Batch(
        "Finance and people",
        (
            ConceptRow(
                "Sales order", "Invoice", "finance", "billed by", "Invoice is kept in Finance."
            ),
            ConceptRow("Plant", "Cost centre", "finance", "charged to", "Cost centre is kept."),
            ConceptRow("Cost centre", "Budget", "finance", "limited by", "Budget is kept."),
            ConceptRow(
                COMPANY_NAME, "Employee", "people", "employs", "Employee is kept in People."
            ),
            RelationRow(
                "Operator",
                "is a",
                "Employee",
                "Operator is an Employee: the same person seen by two domain products.",
            ),
            ConceptRow("Employee", "Certification", "people", "holds", "Certification is kept."),
            ConceptRow(
                "Certification", "Training", "people", "earned through", "Training is kept."
            ),
        ),
    ),
    Batch(
        "Engineering",
        (
            ConceptRow(
                "Product",
                "Specification",
                "engineering",
                "specified by",
                "Specification is kept in Engineering.",
            ),
            ConceptRow("Specification", "Test", "engineering", "validated by", "Test is kept."),
            ConceptRow(
                "Specification",
                "Engineering change",
                "engineering",
                "evolved by",
                "Engineering change is kept.",
            ),
            RelationRow(
                "Engineering change",
                "updates",
                "Bill of materials",
                "Engineering change updates Bill of materials: R&D writes into Supply chain’s product through a declared relation.",
            ),
        ),
    ),
)
