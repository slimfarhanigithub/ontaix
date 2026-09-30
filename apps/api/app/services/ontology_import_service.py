"""Ontology import: map an ontology or hierarchy file to a stored draft tree, then propose it.

`import_ontology` checks the caller's scope, detects the format, reads and maps the file in a
child process with no network and a time and memory limit, and stores the tree for 24 hours
for the actor that created it; no ontology row and no proposal is written. `propose` turns a
selection of the stored drafts, closed under their `requires`, into proposals with origin
`ontology_import` in one all-or-nothing transaction, once. No language model is involved.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import timedelta
from typing import get_args

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.config import get_settings
from app.models.api.drafts import ProposalDraft
from app.models.api.ontology_import import (
    OntologyImportNote,
    OntologyImportResult,
    SkippedItem,
)
from app.models.api.proposal import Proposal as ProposalDto
from app.models.ontology_import.parsed_ontology import OntologyFormat
from app.models.proposals.provenance import Provenance
from app.models.storage.base import NodeKind, ProposalOrigin
from app.models.storage.ontology_import import OntologyImport
from app.repositories import ontology_import_repository, tenant_settings_repository
from app.services import child_process_service, proposal_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import Budget, charge, charge_proposals
from app.utilities.action_text import normalise_action
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.channels import ensure_import_allowed
from app.utilities.clock import get_clock
from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)
from app.utilities.document_text import base_name, file_name_problem
from app.utilities.ontology_formats import detect_format
from app.utilities.ontology_mapping import ExistingConcept, MappedTree, MappingTarget
from app.utilities.ontology_reader import read_and_map
from app.utilities.permissions import Scope, can_propose, can_propose_anywhere
from app.utilities.problems import ProblemError, conflict, forbidden, not_found, validation_failed

logger = logging.getLogger(__name__)

PURGE_AFTER_EXPIRY = timedelta(hours=24)
DEFAULT_LANGUAGES = ("en",)
MAX_LANGUAGES = 10
MAX_WHY_SOURCE_CHARS = 200
INDIVIDUALS = ("skip", "as_concepts")
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")
_DRAFT = TypeAdapter(ProposalDraft)


async def admit_import(session: AsyncSession, caller: Caller) -> None:
    """The checks that run before the upload is read: a proposing role, the `importDocs`
    setting, one import unit."""
    if not can_propose_anywhere(caller.grants, caller.everyone_teaches):
        raise forbidden("Your roles do not allow proposing")
    ensure_import_allowed(await tenant_settings_repository.get(session, caller.tenant_id))
    await charge(Budget.IMPORT, caller.tenant_id, caller.actor_kind.value, caller.user_id)


async def import_ontology(
    session: AsyncSession,
    caller: Caller,
    *,
    raw_file_name: str,
    content_type: str | None,
    data: bytes,
    company_id: str | None,
    parent_concept_id: str | None,
    languages: str | None,
    individuals: str | None,
    domain_key: str | None,
    chosen_format: str | None = None,
) -> OntologyImportResult:
    """Map and store one upload admitted by `admit_import`; nothing is stored on a refusal.
    `chosen_format` replaces the extension and media type as the declared format."""
    config = get_settings()
    file_name = base_name(raw_file_name)
    problem = file_name_problem(file_name)
    if problem:
        raise validation_failed("file", problem)
    company = _uuid("companyId", company_id)
    parent_id = _uuid("parentConceptId", parent_concept_id) if parent_concept_id else None
    tags = _languages(languages)
    chosen = _format(chosen_format)
    individuals = individuals or "skip"
    if individuals not in INDIVIDUALS:
        raise validation_failed("individuals", "individuals is skip or as_concepts")
    if len(data) > config.ontology_import_max_bytes:
        raise _too_large(f"the file is larger than {config.ontology_import_max_bytes} bytes")
    view = await load_view(session, caller.tenant_id)
    target = _target(caller, view, company, parent_id, tags, individuals, domain_key or None)
    try:
        fmt = detect_format(file_name, content_type, data, chosen)
        tree: MappedTree = await child_process_service.run(
            read_and_map,
            (data, fmt, target, _existing(view, company), _existing_relations(view, company)),
            config.ontology_import_parse_timeout_seconds,
            "the ontology file",
        )
    except UnsupportedDocumentError as exc:
        raise ProblemError(415, "unsupported_media_type", str(exc)) from exc
    except DocumentTooLargeError as exc:
        raise _too_large(str(exc)) from exc
    except DocumentUnreadableError as exc:
        raise validation_failed("file", str(exc)) from exc
    row = await ontology_import_repository.create(
        session,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        company_id=company,
        parent_concept_id=parent_id,
        file_name=file_name,
        format=fmt,
        sha256=hashlib.sha256(data).digest(),
        languages=list(tags),
        individuals=individuals,
        drafts=tree.drafts,
        notes=tree.notes,
        skipped=tree.skipped,
    )
    logger.info(
        "ontology import %s: %d drafts, %d skipped from %s",
        row.id,
        len(tree.drafts),
        len(tree.skipped),
        fmt,
    )
    return _result(row)


async def get_import(
    session: AsyncSession, caller: Caller, ontology_import_id: uuid.UUID
) -> OntologyImportResult:
    return _result(await _owned(session, caller, ontology_import_id))


async def propose(
    session: AsyncSession, caller: Caller, ontology_import_id: uuid.UUID, indexes: list[int]
) -> list[ProposalDto]:
    """Create one proposal per selected draft, in draft order, from the stored drafts."""
    row = await _owned(session, caller, ontology_import_id)
    if row.submitted_at is not None:
        raise _submitted()
    selected = _selection(row, indexes)
    if not await ontology_import_repository.claim_submission(session, caller.tenant_id, row.id):
        raise _submitted()
    await charge_proposals(caller, len(selected))
    view = await load_view(session, caller.tenant_id)
    created = []
    for index in selected:
        try:
            draft = _DRAFT.validate_python(row.drafts[index])
        except ValidationError as exc:
            raise validation_failed("indexes", f"draft {index} is not a valid draft") from exc
        source = row.notes[index].get("source", "")[:MAX_WHY_SOURCE_CHARS]
        provenance = Provenance(
            ProposalOrigin.ONTOLOGY_IMPORT, None, f"Imported from {row.file_name} · {source}"
        )
        created.append(
            await proposal_service.create(session, caller, view, draft, provenance=provenance)
        )
    logger.info("ontology import %s: %d proposals", row.id, len(created))
    return [
        readable_proposal(caller.grants, view.proposal_dto(p, view.proposal_artefacts(p)))
        for p in created
    ]


async def purge_expired(session: AsyncSession) -> int:
    """Delete every ontology import more than 24 hours past its expiry."""
    cutoff = get_clock().now() - PURGE_AFTER_EXPIRY
    return await ontology_import_repository.delete_expired_before(session, cutoff)


def _target(
    caller: Caller,
    view: OntologyView,
    company_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    languages: tuple[str, ...],
    individuals: str,
    domain_key: str | None,
) -> MappingTarget:
    """Where the tree goes, after the company, parent and domain checks and the caller's scope."""
    company = view.companies.get(company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    if parent_id is None:
        parent = view.root_of(company_id)
        if parent is None:
            raise not_found("company root")
    else:
        parent = view.concepts.get(parent_id)
        if parent is None or parent.company_id != company_id or parent.dying_at is not None:
            raise not_found("parent concept")
        if parent.pending:
            raise conflict("concept_pending", f"{parent.label} is waiting for approval")
    if not can_propose(
        caller.grants, Scope(company_id, view.domain_key(parent)), caller.everyone_teaches
    ):
        raise forbidden("Your roles do not allow proposing in this company")
    keys = frozenset(view.domains)
    if domain_key is not None and domain_key not in keys:
        raise validation_failed("domainKey", f"unknown domain key {domain_key!r}")
    return MappingTarget(
        company_id=company_id,
        parent_id=parent.id,
        parent_domain_key=view.domain_key(parent) if parent.kind is not NodeKind.ROOT else None,
        domain_keys=keys,
        domain_key=domain_key,
        languages=languages,
        individuals=individuals,
        max_nodes=get_settings().ontology_import_max_nodes,
    )


def _existing(view: OntologyView, company_id: uuid.UUID) -> list[ExistingConcept]:
    """The company's live and pending concepts, oldest first."""
    concepts = sorted(
        (c for c in view.live_concepts() if c.company_id == company_id),
        key=lambda c: (c.born_at, str(c.id)),
    )
    return [ExistingConcept(c.id, c.label, c.parent_id, view.domain_key(c)) for c in concepts]


def _existing_relations(
    view: OntologyView, company_id: uuid.UUID
) -> set[tuple[uuid.UUID, uuid.UUID, str]]:
    ids = {c.id for c in view.live_concepts() if c.company_id == company_id}
    return {
        (r.a_id, r.b_id, normalise_action(r.label))
        for r in view.live_relations()
        if r.a_id in ids and r.b_id in ids
    }


def _selection(row: OntologyImport, indexes: list[int]) -> list[int]:
    """The selected indexes in draft order, when every one exists, none repeats and every
    draft a selected one requires is selected too."""
    if len(set(indexes)) != len(indexes):
        raise validation_failed("indexes", "an index is repeated")
    if any(i < 0 or i >= row.draft_count for i in indexes):
        raise validation_failed("indexes", "an index names no draft")
    chosen = set(indexes)
    for index in indexes:
        missing = [r for r in row.notes[index].get("requires", []) if r not in chosen]
        if missing:
            raise validation_failed(
                "indexes", f"draft {index} requires draft {missing[0]}, which is not selected"
            )
    return sorted(chosen)


async def _owned(
    session: AsyncSession, caller: Caller, ontology_import_id: uuid.UUID
) -> OntologyImport:
    """The caller's own ontology import in its tenant: `404` otherwise, `410` past its expiry."""
    row = await ontology_import_repository.get(session, caller.tenant_id, ontology_import_id)
    if row is None or row.actor_user_id != caller.user_id:
        raise not_found("ontology import")
    if row.expires_at <= get_clock().now():
        raise ProblemError(
            410, "ontology_import_expired", "the ontology import has expired; import it again"
        )
    return row


def _result(row: OntologyImport) -> OntologyImportResult:
    return OntologyImportResult(
        ontology_import_id=row.id,
        expires_at=row.expires_at,
        company_id=row.company_id,
        parent_concept_id=row.parent_concept_id,
        format=row.format,
        languages=list(row.languages),
        individuals=row.individuals,
        drafts=row.drafts,
        notes=[OntologyImportNote.model_validate(n) for n in row.notes],
        skipped=[SkippedItem.model_validate(s) for s in row.skipped],
    )


def _languages(raw: str | None) -> tuple[str, ...]:
    """BCP 47 tags separated by commas, first preferred, at most 10; `en` when none."""
    if raw is None or not raw.strip():
        return DEFAULT_LANGUAGES
    tags = tuple(t.strip() for t in raw.split(","))
    if len(tags) > MAX_LANGUAGES or not all(_LANGUAGE_TAG.match(t) for t in tags):
        raise validation_failed("languages", "at most 10 BCP 47 tags separated by commas")
    return tags


def _format(raw: str | None) -> OntologyFormat | None:
    """The chosen format, None when none is chosen."""
    if raw is None or not raw:
        return None
    if raw not in get_args(OntologyFormat):
        raise validation_failed("format", "format is one of " + ", ".join(get_args(OntologyFormat)))
    return raw  # type: ignore[return-value]


def _uuid(field: str, value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value or "")
    except ValueError as exc:
        raise validation_failed(field, f"{field} is not a UUID") from exc


def _submitted() -> ProblemError:
    return conflict("ontology_import_submitted", "the ontology import was proposed already")


def _too_large(detail: str) -> ProblemError:
    return ProblemError(413, "payload_too_large", detail)
