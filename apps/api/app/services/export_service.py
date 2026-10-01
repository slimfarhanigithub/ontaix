"""Export: the approved model of a company, a domain product or every readable company, as OWL 2,
SKOS or a Word document.

`export` checks that the caller reads the model and the scope, spends one unit of the hourly
`export` budget, reads the approved model of the scope - pending concepts, relations and
attributes left out, and only companies the caller may read - refuses above the concept limit,
audits the scope and format (never the content), and writes the file in a child process within
the time limit. Nothing is written to the model.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.config import get_settings
from app.models.export.export_snapshot import (
    BirthKind,
    ExportAttribute,
    ExportCompany,
    ExportConcept,
    ExportDomain,
    ExportRelation,
    ExportScope,
    ExportSnapshot,
)
from app.models.storage.base import AttributeState, NodeKind, RelationKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.repositories import tenant_repository
from app.services import audit_service, child_process_service
from app.services.company_service import readable_companies
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import Budget, charge
from app.utilities.clock import get_clock
from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.export_writer import FORMATS, write_export
from app.utilities.permissions import can_read_tenant
from app.utilities.problems import ProblemError, bad_request, forbidden, not_found

logger = logging.getLogger(__name__)

SCOPES: tuple[ExportScope, ...] = ("company", "domain", "all")
EXPORT_LANGUAGE = "en"
ALL_SCOPE_NAME = "every readable company"
FORMAT_NAMES: dict[str, str] = {
    "owl": "OWL 2 RDF/XML",
    "owx": "OWL 2 OWL/XML",
    "turtle": "OWL 2 Turtle",
    "jsonld": "OWL 2 JSON-LD",
    "skos": "SKOS Turtle",
    "docx": "Word",
}


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    media_type: str
    file_name: str


@dataclass(frozen=True)
class _Scope:
    kind: ExportScope
    name: str
    file_stem: str
    companies: list[Company]
    domain_product_id: uuid.UUID | None


async def export(
    session: AsyncSession,
    caller: Caller,
    *,
    scope: str | None,
    company_id: str | None,
    domain_product_id: str | None,
    fmt: str | None,
) -> ExportFile:
    if not can_read_tenant(caller.grants):
        raise forbidden("No role grants you access to the model")
    if fmt not in FORMATS:
        raise bad_request("format is owl, owx, turtle, jsonld, skos or docx")
    if scope not in SCOPES:
        raise bad_request("scope is company, domain or all")
    view = await load_view(session, caller.tenant_id)
    chosen = _scope(caller, view, scope, company_id, domain_product_id)
    await charge(Budget.EXPORT, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    config = get_settings()
    tenant = await tenant_repository.get(session, caller.tenant_id)
    snapshot = _snapshot(
        view, caller, chosen, tenant.name if tenant else "", config.export_base_iri
    )
    concepts = sum(1 for c in snapshot.concepts if c.birth != "root")
    if concepts > config.export_max_concepts:
        raise ProblemError(
            413,
            "payload_too_large",
            f"the scope holds more than {config.export_max_concepts} concepts",
        )
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        "export",
        f"{chosen.name} exported as {FORMAT_NAMES[fmt]}",
        True,
        company_ids=[c.id for c in chosen.companies],
    )
    try:
        content: bytes = await child_process_service.run(
            write_export, (snapshot, fmt), config.export_timeout_seconds, "the export"
        )
    except (DocumentTooLargeError, DocumentUnreadableError) as exc:
        raise ProblemError(503, "unavailable", str(exc)) from exc
    info = FORMATS[fmt]
    date = snapshot.exported_at.date().isoformat()
    logger.info("export %s as %s: %d concepts, %d bytes", scope, fmt, concepts, len(content))
    return ExportFile(content, info.media_type, f"ontaix-{chosen.file_stem}-{date}{info.extension}")


def _scope(
    caller: Caller,
    view: OntologyView,
    scope: ExportScope,
    company_id: str | None,
    domain_product_id: str | None,
) -> _Scope:
    readable = {c.id: c for c in readable_companies(caller, view)}
    if scope == "all":
        return _Scope("all", ALL_SCOPE_NAME, "all", list(readable.values()), None)
    if scope == "company":
        company = readable.get(_uuid("companyId", company_id))
        if company is None:
            raise not_found("company")
        return _Scope("company", company.name, _stem(company.key), [company], None)
    product = view.domain_products.get(_uuid("domainProductId", domain_product_id))
    company = readable.get(product.company_id) if product is not None else None
    if product is None or company is None:
        raise not_found("domain product")
    name = f"{view.domains[product.template_key].name} of {company.name}"
    stem = f"{_stem(company.key)}-{product.template_key}"
    return _Scope("domain", name, stem, [company], product.id)


def _snapshot(
    view: OntologyView, caller: Caller, chosen: _Scope, tenant_name: str, base_iri: str
) -> ExportSnapshot:
    readable = {c.id for c in readable_companies(caller, view)}
    scope_companies = {c.id for c in chosen.companies}
    approved = {c.id: c for c in view.live_concepts() if not c.pending and c.company_id in readable}

    def in_scope(concept: Concept) -> bool:
        if concept.company_id not in scope_companies:
            return False
        if chosen.domain_product_id is None or concept.kind is NodeKind.ROOT:
            return True
        return concept.domain_product_id == chosen.domain_product_id

    members = sorted(
        (c for c in approved.values() if in_scope(c)),
        key=lambda c: (c.company_id not in scope_companies, c.born_at, str(c.id)),
    )
    member_ids = {c.id for c in members}
    births = {c.birth_relation_id for c in view.concepts.values() if c.birth_relation_id}
    relations: list[ExportRelation] = []
    outside_ids: set[uuid.UUID] = set()
    for relation in sorted(view.live_relations(), key=lambda r: (r.created_at, str(r.id))):
        if relation.pending or relation.id in births:
            continue
        if relation.a_id not in approved or relation.b_id not in approved:
            continue
        ends = {relation.a_id, relation.b_id}
        if not ends & member_ids:
            continue
        outside_ids.update(ends - member_ids)
        relations.append(
            ExportRelation(relation.a_id, relation.b_id, relation.kind.value, relation.label)
        )
    for concept in members:
        if concept.parent_id is not None and concept.parent_id not in member_ids:
            if concept.parent_id in approved:
                outside_ids.add(concept.parent_id)
    outside = sorted((approved[i] for i in outside_ids), key=lambda c: (c.born_at, str(c.id)))
    outside_companies = {c.company_id for c in outside} - scope_companies
    domain_keys: dict[uuid.UUID, set[str]] = {c.id: set() for c in chosen.companies}
    for concept in members:
        key = view.domain_key(concept)
        if key is not None:
            domain_keys[concept.company_id].add(key)
    used = set().union(*domain_keys.values()) if domain_keys else set()
    order = sorted(view.domains.values(), key=lambda t: t.position)
    return ExportSnapshot(
        scope=chosen.kind,
        scope_name=chosen.name,
        tenant_name=tenant_name,
        exported_at=get_clock().now(),
        base_iri=base_iri,
        language=EXPORT_LANGUAGE,
        companies=[
            _company(c, [t.key for t in order if t.key in domain_keys[c.id]])
            for c in chosen.companies
        ],
        domains=[
            ExportDomain(t.key, t.name, t.owner, view.effective_color(t.key))
            for t in order
            if t.key in used
        ],
        concepts=[_concept(view, c) for c in members],
        relations=relations,
        outside=[_concept(view, c, attributes=False) for c in outside],
        outside_companies=[
            _company(view.companies[i], [])
            for i in sorted(outside_companies, key=lambda i: view.companies[i].position)
        ],
    )


def _company(company: Company, domain_keys: list[str]) -> ExportCompany:
    return ExportCompany(company.id, company.key, company.name, company.sub, tuple(domain_keys))


def _concept(view: OntologyView, concept: Concept, attributes: bool = True) -> ExportConcept:
    birth: BirthKind
    if concept.kind is NodeKind.ROOT:
        birth = "root"
    else:
        relation = view.relations.get(concept.birth_relation_id or uuid.UUID(int=0))
        birth = "spec" if relation is not None and relation.kind is RelationKind.ISA else "birth"
    return ExportConcept(
        id=concept.id,
        company_id=concept.company_id,
        label=concept.label,
        birth=birth,
        domain_key=view.domain_key(concept),
        parent_id=concept.parent_id if birth != "root" else None,
        birth_action=concept.birth_action if birth == "birth" else None,
        birth_reverse=concept.birth_reverse if birth == "birth" else False,
        rule=concept.rule if birth == "spec" else None,
        attributes=tuple(
            ExportAttribute(a.name, a.type.value, a.value, a.col, a.fill)
            for a in sorted(view.attributes.get(concept.id, []), key=lambda a: a.name.lower())
            if a.state is AttributeState.APPROVED
        )
        if attributes
        else (),
    )


def _uuid(field: str, value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value or "")
    except ValueError as exc:
        raise bad_request(f"{field} is required and is a UUID") from exc


def _stem(company_key: str) -> str:
    return company_key.strip("-") or "company"
