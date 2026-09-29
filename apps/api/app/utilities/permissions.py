"""Native authorisation as a pure function over a caller's role grants.

Roles reach a user only through group membership and group role assignments. A grant holds on
the tenant (everything), on one company (its domain products included) or on one domain product
family (that template key in every company). A proposal's scope is its domain product when it
has one, otherwise its company, otherwise the tenant. A proposal whose relation joins two
companies has the tenant as its scope, so only a tenant-wide grant decides it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.storage.base import RoleName, ScopeKind

APPROVING_ROLES = frozenset({RoleName.OWNER, RoleName.GOVERNOR})
PROPOSING_ROLES = frozenset({RoleName.OWNER, RoleName.BUILDER, RoleName.AGENT})
BUILDING_ROLES = frozenset({RoleName.OWNER, RoleName.BUILDER})
AUDIT_ROLES = frozenset({RoleName.ADMINISTRATOR, RoleName.GOVERNOR, RoleName.AUDITOR})


@dataclass(frozen=True)
class Grant:
    """One role a caller holds on one scope."""

    role: RoleName
    scope_kind: ScopeKind
    company_id: uuid.UUID | None = None
    domain_key: str | None = None

    def contains(self, scope: Scope) -> bool:
        """True when this grant's scope encloses `scope`."""
        if self.scope_kind is ScopeKind.TENANT:
            return True
        if self.scope_kind is ScopeKind.COMPANY:
            return scope.company_id is not None and scope.company_id == self.company_id
        return scope.domain_key is not None and scope.domain_key == self.domain_key


@dataclass(frozen=True)
class Scope:
    """Where an action happens: a domain product of a company, a company, or the tenant."""

    company_id: uuid.UUID | None = None
    domain_key: str | None = None

    @classmethod
    def tenant(cls) -> Scope:
        return cls()


def can_read(grants: tuple[Grant, ...], company_id: uuid.UUID) -> bool:
    """Any role whose scope reaches the company grants read access to it.

    A domain family spans every company, so a domain-scoped role reads every company.
    """
    scope = Scope(company_id=company_id)
    return any(g.contains(scope) or g.scope_kind is ScopeKind.DOMAIN for g in grants)


def can_read_proposal(grants: tuple[Grant, ...], company_ids: set[uuid.UUID]) -> bool:
    """A proposal is readable when every company it touches is; a tenant-level one needs a
    tenant-wide grant."""
    if not company_ids:
        return any(g.scope_kind is ScopeKind.TENANT for g in grants)
    return all(can_read(grants, company_id) for company_id in company_ids)


def can_read_tenant(grants: tuple[Grant, ...]) -> bool:
    """A caller with at least one role may read tenant-level resources."""
    return len(grants) > 0


def can_propose(grants: tuple[Grant, ...], scope: Scope, everyone_teaches: bool) -> bool:
    """Owner, Builder or Agent in scope; Member too when the tenant lets everyone teach."""
    for g in grants:
        if g.role in PROPOSING_ROLES and g.contains(scope):
            return True
        if everyone_teaches and g.role is RoleName.MEMBER and g.contains(scope):
            return True
    return False


def can_propose_as_builder(grants: tuple[Grant, ...], scope: Scope) -> bool:
    """`proposal.create` in scope through the Owner or Builder role only: what concept expansion
    and whole-document extraction require, since both spend large model budgets. Members who
    teach through `everyoneTeaches` and agents never qualify."""
    return any(g.role in BUILDING_ROLES and g.contains(scope) for g in grants)


def can_propose_anywhere(grants: tuple[Grant, ...], everyone_teaches: bool) -> bool:
    """`proposal.create` in at least one scope."""
    return any(
        g.role in PROPOSING_ROLES or (everyone_teaches and g.role is RoleName.MEMBER)
        for g in grants
    )


def can_approve(grants: tuple[Grant, ...], scope: Scope) -> bool:
    """Owner in scope or Governor in an enclosing scope; Builders never approve."""
    return any(g.role in APPROVING_ROLES and g.contains(scope) for g in grants)


def holds_approving_role(grants: tuple[Grant, ...]) -> bool:
    """Owner or Governor on any scope: the caller may decide at least some proposals."""
    return any(g.role in APPROVING_ROLES for g in grants)


def can_manage(grants: tuple[Grant, ...]) -> bool:
    """Administrator at tenant scope."""
    return any(
        g.role is RoleName.ADMINISTRATOR and g.scope_kind is ScopeKind.TENANT for g in grants
    )


def can_read_audit(grants: tuple[Grant, ...]) -> bool:
    return any(g.role in AUDIT_ROLES for g in grants)


def can_read_audit_entry(
    grants: tuple[Grant, ...], company_ids: list[uuid.UUID], domain_key: str | None
) -> bool:
    """`audit.read` in one scope that contains every listed company, or on the domain scope
    named by `domain_key`; an empty list is tenant-wide and needs `audit.read` at any scope.

    A domain scope contains no whole company, so a domain-scoped reader sees the entries of its
    domain in every company and the tenant-wide entries, never other company-level entries.
    """
    audit_grants = [g for g in grants if g.role in AUDIT_ROLES]
    if not company_ids:
        return bool(audit_grants)
    return any(
        (g.scope_kind is ScopeKind.DOMAIN and domain_key is not None and g.domain_key == domain_key)
        or all(g.contains(Scope(company_id=company_id)) for company_id in company_ids)
        for g in audit_grants
    )


def permission_names(grants: tuple[Grant, ...], everyone_teaches: bool) -> list[str]:
    """Coarse permission list the Studio uses to enable buttons."""
    names: list[str] = []
    if can_read_tenant(grants):
        names.extend(["model.read", "view.write"])
    if can_propose_anywhere(grants, everyone_teaches):
        names.append("proposal.create")
    if holds_approving_role(grants):
        names.extend(["proposal.approve", "proposal.second_approve", "proposal.reject"])
    if can_manage(grants):
        names.extend(
            [
                "settings.write",
                "appearance.write",
                "company.create",
                "source.manage",
                "group.manage",
                "agent.manage",
            ]
        )
    if can_read_audit(grants):
        names.extend(["directory.read", "audit.read"])
    return names
