"""In-memory view of one tenant's ontology, loaded once per request, with every DTO builder.

The view holds the ORM rows of the tenant in dictionaries and derives what the contract asks
for: colours, counters, relation counts, proposal readiness and headings. Services that mutate
rows register the new or removed rows on the view so that DTOs built afterwards stay current.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.api.attribute import Attribute as AttributeDto
from app.models.api.company import Company as CompanyDto
from app.models.api.company import CompanyCounts
from app.models.api.concept import Concept as ConceptDto
from app.models.api.domain_product import DomainProduct as DomainProductDto
from app.models.api.domain_product import DomainProductCounts
from app.models.api.proposal import Approval, Artefacts
from app.models.api.proposal import Proposal as ProposalDto
from app.models.api.relation import Relation as RelationDto
from app.models.storage.app_user import AppUser
from app.models.storage.attribute import Attribute
from app.models.storage.base import NodeKind, ProposalType, RelationKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.domain_product import DomainProduct
from app.models.storage.domain_template import DomainTemplate
from app.models.storage.proposal import Proposal
from app.models.storage.proposal_approval import ProposalApproval
from app.models.storage.relation import Relation
from app.models.storage.tenant_settings import TenantSettings
from app.repositories import (
    app_user_repository,
    attribute_repository,
    company_repository,
    concept_repository,
    domain_product_repository,
    domain_template_repository,
    proposal_approval_repository,
    relation_repository,
    tenant_settings_repository,
)
from app.utilities.layout import ROOT_COLOR
from app.utilities.proposal_relations import own_relation_ids
from app.utilities.versions import version_label

logger = logging.getLogger(__name__)

HEADINGS: dict[ProposalType, str] = {
    ProposalType.CONCEPT: "New concept",
    ProposalType.SPEC: "Specialisation",
    ProposalType.RELATION: "Relation",
    ProposalType.CHANGE: "Change",
    ProposalType.SOURCE: "Data source",
    ProposalType.BIND: "Binding",
    ProposalType.ATTR: "Attribute",
}

PREDICATE_BOTH_ENDS_APPROVED = "both_ends_approved"
PREDICATES = frozenset({PREDICATE_BOTH_ENDS_APPROVED})
MAX_LINEAGE_HOPS = 50


@dataclass
class OntologyView:
    tenant_id: uuid.UUID
    settings: TenantSettings | None
    templates: dict[str, DomainTemplate]
    companies: dict[uuid.UUID, Company]
    domain_products: dict[uuid.UUID, DomainProduct]
    concepts: dict[uuid.UUID, Concept]
    relations: dict[uuid.UUID, Relation]
    attributes: dict[uuid.UUID, list[Attribute]]
    users: dict[uuid.UUID, AppUser]
    approvals: dict[uuid.UUID, list[ProposalApproval]] = field(default_factory=dict)

    def register_concept(self, concept: Concept) -> None:
        self.concepts[concept.id] = concept

    def register_relation(self, relation: Relation) -> None:
        self.relations[relation.id] = relation

    def register_domain_product(self, product: DomainProduct) -> None:
        self.domain_products[product.id] = product

    def register_company(self, company: Company) -> None:
        self.companies[company.id] = company

    def register_attribute(self, attribute: Attribute) -> None:
        self.attributes.setdefault(attribute.concept_id, []).append(attribute)

    def forget_attribute(self, attribute: Attribute) -> None:
        kept = [a for a in self.attributes.get(attribute.concept_id, []) if a.id != attribute.id]
        self.attributes[attribute.concept_id] = kept

    def attribute(self, attribute_id: uuid.UUID | None) -> Attribute | None:
        if attribute_id is None:
            return None
        return next(
            (a for rows in self.attributes.values() for a in rows if a.id == attribute_id), None
        )

    def attribute_named(self, concept_id: uuid.UUID, name: str) -> Attribute | None:
        """The concept's attribute of that name, compared case-insensitively."""
        wanted = name.lower()
        return next(
            (a for a in self.attributes.get(concept_id, []) if a.name.lower() == wanted), None
        )

    def register_approval(self, approval: ProposalApproval) -> None:
        self.approvals.setdefault(approval.proposal_id, []).append(approval)

    def forget_concept(self, concept_id: uuid.UUID) -> None:
        self.concepts.pop(concept_id, None)
        for rid in [r.id for r in self.relations.values() if concept_id in (r.a_id, r.b_id)]:
            self.relations.pop(rid, None)

    def forget_relation(self, relation_id: uuid.UUID) -> None:
        self.relations.pop(relation_id, None)

    def forget_company(self, company_id: uuid.UUID) -> None:
        for cid in [c.id for c in self.concepts.values() if c.company_id == company_id]:
            self.forget_concept(cid)
        for pid in [p.id for p in self.domain_products.values() if p.company_id == company_id]:
            self.domain_products.pop(pid, None)
        self.companies.pop(company_id, None)

    def live_concepts(self) -> list[Concept]:
        return [c for c in self.concepts.values() if c.dying_at is None]

    def live_relations(self) -> list[Relation]:
        return [r for r in self.relations.values() if r.dying_at is None]

    def find_label(self, company_id: uuid.UUID, label: str) -> Concept | None:
        """Case-insensitive label lookup in one company; pending cells count, dying ones do not."""
        wanted = label.lower()
        for c in self.concepts.values():
            if c.company_id == company_id and c.dying_at is None and c.label.lower() == wanted:
                return c
        return None

    def root_of(self, company_id: uuid.UUID) -> Concept | None:
        for c in self.concepts.values():
            if c.company_id == company_id and c.kind is NodeKind.ROOT:
                return c
        return None

    def domain_product_by_key(self, company_id: uuid.UUID, key: str) -> DomainProduct | None:
        for p in self.domain_products.values():
            if p.company_id == company_id and p.template_key == key:
                return p
        return None

    def relations_touching(self, concept_id: uuid.UUID) -> list[Relation]:
        return [r for r in self.live_relations() if concept_id in (r.a_id, r.b_id)]

    def children_of(self, concept_id: uuid.UUID) -> list[Concept]:
        return [
            c for c in self.concepts.values() if c.parent_id == concept_id and c.dying_at is None
        ]

    def descendants_of(self, concept_id: uuid.UUID) -> list[Concept]:
        out: list[Concept] = []
        stack = [concept_id]
        seen: set[uuid.UUID] = set()
        while stack:
            current = stack.pop()
            for child in self.children_of(current):
                if child.id in seen:
                    continue
                seen.add(child.id)
                out.append(child)
                stack.append(child.id)
        return out

    def ancestors_of(self, concept_id: uuid.UUID) -> list[Concept]:
        """From the root down to the parent."""
        out: list[Concept] = []
        current = self.concepts.get(concept_id)
        hops = 0
        while current is not None and current.parent_id is not None and hops < MAX_LINEAGE_HOPS:
            parent = self.concepts.get(current.parent_id)
            if parent is None:
                break
            out.insert(0, parent)
            current = parent
            hops += 1
        return out

    def descends(self, concept_id: uuid.UUID, ancestor_id: uuid.UUID) -> bool:
        current = self.concepts.get(concept_id)
        hops = 0
        while current is not None and current.parent_id is not None and hops < MAX_LINEAGE_HOPS:
            if current.parent_id == ancestor_id:
                return True
            current = self.concepts.get(current.parent_id)
            hops += 1
        return False

    def effective_color(self, template_key: str) -> str:
        overrides = self.settings.colors if self.settings is not None else {}
        return str(overrides.get(template_key) or self.templates[template_key].color)

    def concept_color(self, concept: Concept) -> str:
        product = self.domain_products.get(concept.domain_product_id or uuid.UUID(int=0))
        return self.effective_color(product.template_key) if product else ROOT_COLOR

    def domain_name(self, concept: Concept) -> str | None:
        product = (
            self.domain_products.get(concept.domain_product_id)
            if concept.domain_product_id
            else None
        )
        return self.templates[product.template_key].name if product else None

    def domain_key(self, concept: Concept) -> str | None:
        product = (
            self.domain_products.get(concept.domain_product_id)
            if concept.domain_product_id
            else None
        )
        return product.template_key if product else None

    def proposal_domain_key(self, proposal: Proposal) -> str | None:
        """The template key of the proposal's domain product, or None when it has none."""
        product = (
            self.domain_products.get(proposal.domain_product_id)
            if proposal.domain_product_id
            else None
        )
        return product.template_key if product else None

    def domain_product_dto(self, product: DomainProduct) -> DomainProductDto:
        template = self.templates[product.template_key]
        members = [c for c in self.live_concepts() if c.domain_product_id == product.id]
        return DomainProductDto(
            id=product.id,
            company_id=product.company_id,
            key=product.template_key,
            name=template.name,
            owner=template.owner,
            color=self.effective_color(product.template_key),
            revision=product.revision,
            version=version_label(product.revision),
            hidden=product.hidden,
            counts=DomainProductCounts(
                members=len(members),
                pending=sum(1 for c in members if c.pending),
                bound=0,
            ),
        )

    def company_domain_products(self, company_id: uuid.UUID) -> list[DomainProduct]:
        products = [p for p in self.domain_products.values() if p.company_id == company_id]
        return sorted(products, key=lambda p: self.templates[p.template_key].position)

    def company_dto(self, company: Company) -> CompanyDto:
        root = self.root_of(company.id)
        concepts = [
            c
            for c in self.live_concepts()
            if c.company_id == company.id and c.kind is NodeKind.CONCEPT
        ]
        company_concept_ids = {c.id for c in self.concepts.values() if c.company_id == company.id}
        equivalences = sum(
            1
            for r in self.live_relations()
            if r.kind is RelationKind.SAME
            and (r.a_id in company_concept_ids or r.b_id in company_concept_ids)
        )
        domains_with_cells = len({c.domain_product_id for c in concepts if c.domain_product_id})
        return CompanyDto(
            id=company.id,
            key=company.key,
            name=company.name,
            sub=company.sub,
            position=company.position,
            is_home=company.is_home,
            root_id=root.id if root else uuid.UUID(int=0),
            domain_products=[
                self.domain_product_dto(p) for p in self.company_domain_products(company.id)
            ],
            counts=CompanyCounts(
                concepts=len(concepts),
                sources=0,
                equivalences=equivalences,
                bound=0,
                percent_bound=0,
                domains_with_cells=domains_with_cells,
            ),
            dying_at=company.dying_at,
        )

    def concept_dto(self, concept: Concept) -> ConceptDto:
        touching = self.relations_touching(concept.id)
        is_spec = any(r.kind is RelationKind.ISA and r.a_id == concept.id for r in touching)
        if concept.pending:
            state = "awaiting approval"
        elif "certified" in concept.sub:
            state = "certified"
        else:
            state = "approved"
        return ConceptDto(
            id=concept.id,
            company_id=concept.company_id,
            kind=concept.kind.value,
            label=concept.label,
            sub=concept.sub,
            domain_product_id=concept.domain_product_id,
            domain_key=self.domain_key(concept),
            color=self.concept_color(concept),
            rule=concept.rule,
            pending=concept.pending,
            conflict=concept.conflict,
            parent_id=concept.parent_id,
            birth_relation_id=concept.birth_relation_id,
            born_at=concept.born_at,
            x=concept.x,
            y=concept.y,
            pinned=concept.pinned,
            dying_at=concept.dying_at,
            bound=None,
            attributes=[attribute_dto(a) for a in self.attributes.get(concept.id, [])],
            relation_count=len(touching),
            state=state,
            is_specialisation=is_spec,
        )

    def relation_dto(self, relation: Relation) -> RelationDto:
        a = self.concepts[relation.a_id]
        b = self.concepts[relation.b_id]
        company_ids = [a.company_id] + ([b.company_id] if b.company_id != a.company_id else [])
        a_domain, b_domain = self.domain_name(a), self.domain_name(b)
        if a.domain_product_id == b.domain_product_id:
            scope = a_domain or "company"
        else:
            scope = f"{a_domain or 'company'} → {b_domain or 'company'}"
        return RelationDto(
            id=relation.id,
            a_id=relation.a_id,
            b_id=relation.b_id,
            a_label=a.label,
            b_label=b.label,
            kind=relation.kind.value,
            label=relation.label,
            rest=float(relation.rest),
            seed=relation.seed,
            pending=relation.pending,
            dying_at=relation.dying_at,
            company_ids=company_ids,
            scope=scope,
            state="awaiting approval" if relation.pending else "approved",
        )

    def readiness(self, proposal: Proposal) -> tuple[bool, str | None]:
        """Evaluate the proposal's dependencies; returns `(ready, waitFor)`."""
        for dep in proposal.deps:
            if dep == PREDICATE_BOTH_ENDS_APPROVED:
                if not self._both_ends_approved(proposal):
                    return False, proposal.wait_for or "a previous item"
                continue
            if proposal.company_id is None:
                return False, proposal.wait_for or str(dep)
            found = self.find_label(proposal.company_id, str(dep))
            if found is None or found.pending or found.dying_at is not None:
                return False, proposal.wait_for or str(dep)
        return True, None

    def proposal_dto(self, proposal: Proposal, artefacts: Artefacts | None = None) -> ProposalDto:
        ready, wait_for = self.readiness(proposal)
        product = (
            self.domain_products.get(proposal.domain_product_id)
            if proposal.domain_product_id
            else None
        )
        heading = HEADINGS[proposal.type]
        if product is not None and proposal.type is not ProposalType.RELATION:
            heading += f" · {self.templates[product.template_key].name}"
        proposer_user = (
            self.users.get(proposal.proposer_user_id) if proposal.proposer_user_id else None
        )
        return ProposalDto(
            id=proposal.id,
            type=proposal.type.value,
            change_kind=proposal.change_kind.value if proposal.change_kind else None,
            state=proposal.state.value,
            title=proposal.title,
            heading=heading,
            color=proposal.color,
            company_id=proposal.company_id,
            domain_product_id=proposal.domain_product_id,
            parent_label=proposal.parent_label,
            deps=[str(d) for d in proposal.deps],
            ready=ready,
            wait_for=wait_for if not ready else proposal.wait_for,
            html=proposal.html,
            why=proposal.why,
            caption=proposal.caption,
            concept_id=proposal.concept_id,
            relation_id=proposal.relation_id,
            relation_ids=list(proposal.relation_ids or []),
            source_id=proposal.source_id,
            binding_ids=list(proposal.binding_ids or []),
            attribute_id=proposal.attribute_id,
            proposer=Actor(
                kind=proposal.proposer_kind.value,
                id=proposal.proposer_user_id or proposal.proposer_agent_id,
                name=proposer_user.name if proposer_user else None,
            ),
            origin=proposal.origin.value,
            origin_detail=proposal.origin_detail,
            approvals=[
                Approval(
                    ordinal=a.ordinal,
                    user_id=a.user_id,
                    user_name=self.users[a.user_id].name if a.user_id in self.users else None,
                    approved_at=a.approved_at,
                )
                for a in self.approvals.get(proposal.id, [])
            ],
            bulk=proposal.bulk,
            created_at=proposal.created_at,
            decided_at=proposal.decided_at,
            artefacts=artefacts,
        )

    def proposal_artefacts(self, proposal: Proposal) -> Artefacts:
        """Current state of the rows a proposal created, for the response and the event."""
        concepts = []
        if proposal.concept_id and proposal.concept_id in self.concepts:
            concepts.append(self.concept_dto(self.concepts[proposal.concept_id]))
        relation_ids = own_relation_ids(proposal)
        relations = [
            self.relation_dto(self.relations[rid])
            for rid in relation_ids
            if rid in self.relations
            and self.relations[rid].a_id in self.concepts
            and self.relations[rid].b_id in self.concepts
        ]
        products = []
        if proposal.domain_product_id and proposal.domain_product_id in self.domain_products:
            products.append(
                self.domain_product_dto(self.domain_products[proposal.domain_product_id])
            )
        attribute = self.attribute(proposal.attribute_id)
        return Artefacts(
            concepts=concepts,
            relations=relations,
            attributes=[attribute_dto(attribute)] if attribute is not None else [],
            domain_products=products,
        )

    def _both_ends_approved(self, proposal: Proposal) -> bool:
        relation = self.relations.get(proposal.relation_id) if proposal.relation_id else None
        if relation is None:
            return False
        a, b = self.concepts.get(relation.a_id), self.concepts.get(relation.b_id)
        return all(c is not None and not c.pending and c.dying_at is None for c in (a, b))


def attribute_dto(attribute: Attribute) -> AttributeDto:
    return AttributeDto(
        id=attribute.id,
        concept_id=attribute.concept_id,
        source_id=attribute.source_id,
        name=attribute.name,
        type=attribute.type.value,
        col=attribute.col,
        fill=attribute.fill,
        value=attribute.value,
        state=attribute.state.value,
    )


async def load_view(
    session: AsyncSession, tenant_id: uuid.UUID, proposals: list[Proposal] | None = None
) -> OntologyView:
    """Load every ontology row of the tenant, plus the approvals of the given proposals."""
    templates = await domain_template_repository.list_in_ring_order(session)
    attributes: dict[uuid.UUID, list[Attribute]] = defaultdict(list)
    for attribute in await attribute_repository.list_for_tenant(session, tenant_id):
        attributes[attribute.concept_id].append(attribute)
    view = OntologyView(
        tenant_id=tenant_id,
        settings=await tenant_settings_repository.get(session, tenant_id),
        templates={t.key: t for t in templates},
        companies={c.id: c for c in await company_repository.list_for_tenant(session, tenant_id)},
        domain_products={
            p.id: p for p in await domain_product_repository.list_for_tenant(session, tenant_id)
        },
        concepts={c.id: c for c in await concept_repository.list_for_tenant(session, tenant_id)},
        relations={r.id: r for r in await relation_repository.list_for_tenant(session, tenant_id)},
        attributes=dict(attributes),
        users={u.id: u for u in await app_user_repository.list_for_tenant(session, tenant_id)},
    )
    if proposals:
        for approval in await proposal_approval_repository.list_for_proposals(
            session, tenant_id, [p.id for p in proposals]
        ):
            view.register_approval(approval)
    return view
