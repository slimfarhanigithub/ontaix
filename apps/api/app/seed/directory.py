"""The fixture tenant's directory: the seven default groups and a small set of dev users.

Users sign in through the `dev` issuer with their e-mail as subject, so `X-Ontaix-User: <email>`
identifies them locally. The e-mail domain belongs to the fictional Northwind Industries.
"""

from __future__ import annotations

from dataclasses import dataclass

TENANT_SLUG = "demo"
TENANT_NAME = "Ontaix demo"
DEV_ISSUER = "dev"


@dataclass(frozen=True)
class SeedUser:
    email: str
    name: str
    department: str


@dataclass(frozen=True)
class SeedRole:
    role: str
    scope_kind: str
    scope_domain_key: str | None = None


@dataclass(frozen=True)
class SeedGroup:
    name: str
    description: str
    members: tuple[str, ...]
    roles: tuple[SeedRole, ...]


USERS: tuple[SeedUser, ...] = (
    SeedUser("marta.hale@northwind.com", "Marta Hale", "Production"),
    SeedUser("tom.reiss@northwind.com", "Tom Reiss", "Supply chain"),
    SeedUser("lena.voss@northwind.com", "Lena Voss", "Sales"),
    SeedUser("hugo.brandt@northwind.com", "Hugo Brandt", "Quality"),
    SeedUser("ines.marchetti@northwind.com", "Ines Marchetti", "Finance"),
    SeedUser("sam.okafor@northwind.com", "Sam Okafor", "IT"),
    SeedUser("priya.nair@northwind.com", "Priya Nair", "People"),
    SeedUser("felix.grau@northwind.com", "Felix Grau", "Finance"),
    SeedUser("demo@northwind.com", "Demo User", "Demo"),
)

EVERYONE = tuple(u.email for u in USERS)

GROUPS: tuple[SeedGroup, ...] = (
    SeedGroup(
        "Plant operations · owners",
        "Owns the Production domain product",
        ("marta.hale@northwind.com",),
        (SeedRole("owner", "domain", "production"),),
    ),
    SeedGroup(
        "Procurement · builders",
        "Models and binds Supply chain",
        ("tom.reiss@northwind.com",),
        (SeedRole("builder", "domain", "supply"),),
    ),
    SeedGroup(
        "Commercial · owners",
        "Owns Sales",
        ("lena.voss@northwind.com",),
        (SeedRole("owner", "domain", "sales"),),
    ),
    SeedGroup(
        "Governance board",
        "Second approver for certification, deletions and conflicts",
        ("hugo.brandt@northwind.com", "ines.marchetti@northwind.com"),
        (SeedRole("governor", "tenant"),),
    ),
    SeedGroup(
        "Data platform team",
        "Connects sources, administers the portal",
        ("sam.okafor@northwind.com",),
        (SeedRole("administrator", "tenant"), SeedRole("builder", "tenant")),
    ),
    SeedGroup("All employees", "Reads the model", EVERYONE, (SeedRole("member", "tenant"),)),
    SeedGroup(
        "PE due-diligence team",
        "Time-boxed read access across the portfolio",
        ("felix.grau@northwind.com",),
        (SeedRole("auditor", "tenant"),),
    ),
    # One person who can do everything, so a demo runs in a single tab. It deliberately sets
    # aside separation of duties and exists only in this development and test seed.
    SeedGroup(
        "Demo · full access",
        "Teaches, approves and administers everything, for demonstrations",
        ("demo@northwind.com",),
        (
            SeedRole("administrator", "tenant"),
            SeedRole("builder", "tenant"),
            SeedRole("governor", "tenant"),
            SeedRole("auditor", "tenant"),
        ),
    ),
)

# The seed proposes as the tenant-wide Builder and approves as a Governor.
PROPOSER_EMAIL = "sam.okafor@northwind.com"
APPROVER_EMAIL = "hugo.brandt@northwind.com"
