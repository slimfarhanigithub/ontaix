"""Capturing lessons from human decisions.

A teach parse by a user is recorded while learning is on for the company; a batch citing it
links each created proposal to the stored draft it came from, and proposals made from stored
expansions and extractions are linked to those. A decision on a linked proposal then teaches:
an approval adds the approved structure to the source's lesson; a direct rejection stores the
rejected draft as a negative; an approval that follows a rejection by the same user on the same
subject, or an edited draft, becomes a correction, which supersedes the source's approvals and
may learn a speech alias. An approved rename of a concept born from speech learns an alias too.
Deleting concepts retires the lessons and aliases that named them, and turns a lesson approved
in the last 24 hours into a negative. Agents never teach, and capture never fails a decision:
it runs in a savepoint and a failure is logged.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.clients.db_client import tenant_session
from app.config import get_settings
from app.models.api.teach import TeachResult
from app.models.storage.base import ActorKind, ChangeKind, ProposalOrigin, ProposalType
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.learning_example import LearningExample
from app.models.storage.proposal import Proposal
from app.models.storage.proposal_learning_source import ProposalLearningSource
from app.models.storage.teach_parse import TeachParse
from app.repositories import (
    company_alias_repository,
    company_repository,
    concept_expansion_repository,
    document_extraction_job_repository,
    document_import_sentence_repository,
    learning_example_repository,
    proposal_learning_source_repository,
    proposal_repository,
    teach_parse_repository,
)
from app.services import learning_service
from app.services.ontology_view_service import OntologyView
from app.utilities.clock import get_clock
from app.utilities.learning_alias import is_alias, storable
from app.utilities.learning_structure import (
    LabelOf,
    compact,
    draft_key,
    fold,
    merged,
    new_labels,
    structure,
    touched,
)

logger = logging.getLogger(__name__)

RECENT_APPROVAL = timedelta(hours=24)
# A teach session lives two hours: a rejection older than that is never in the same session.
SESSION_LIFETIME = timedelta(hours=2)
MAX_SOURCE_CHARS = 4000
MAX_PARSE_BYTES = 262144
MAX_LESSON_BYTES = 65536
MAX_DRAFT_INDEX = 4999
MAX_IDS = 200
KIND_TEACH = "teach"
KIND_EXPAND = "expand"
KIND_EXTRACTION = "extraction"


@dataclass(frozen=True)
class _Source:
    """The model output a linked proposal came from."""

    text: str
    origin: ProposalOrigin
    task: str
    drafts: list[dict[str, Any]]
    parse: TeachParse | None


async def record_parse(
    caller: Caller,
    company: Company,
    session_id: uuid.UUID | None,
    origin: str,
    source_text: str,
    result: TeachResult,
) -> uuid.UUID | None:
    """Store a user's parse for later linking, in a short transaction of its own; None when
    nothing is recorded (an agent, learning off, no draft, or a failure)."""
    if caller.actor_kind is not ActorKind.USER or not learning_service.enabled(company):
        return None
    text = source_text.strip()[:MAX_SOURCE_CHARS]
    if not result.drafts or not text:
        return None
    output = {
        "intents": [i.model_dump(mode="json", by_alias=True) for i in result.intents],
        "drafts": result.drafts,
    }
    if _bytes(output) > MAX_PARSE_BYTES:
        return None
    try:
        async with tenant_session(caller.tenant_id) as session:
            row = await teach_parse_repository.create(
                session,
                tenant_id=caller.tenant_id,
                company_id=company.id,
                actor_user_id=caller.user_id,
                session_id=session_id,
                origin=ProposalOrigin(origin),
                source_text=text,
                extractor=result.extractor,
                model_output=output,
            )
            await session.commit()
            return row.id
    except Exception:
        logger.warning("recording a teach parse for learning failed; the parse is not linked")
        return None


async def link_batch(
    session: AsyncSession,
    caller: Caller,
    parse_id: uuid.UUID | None,
    drafts: list[Any],
    proposals: list[Proposal],
) -> None:
    """Link each created proposal to the stored draft of the cited parse it matches; an
    unmatched draft is linked as edited. A parse of another user, another company, another
    tenant or past its expiry is ignored."""
    if parse_id is None:
        return
    parse = await teach_parse_repository.get_unexpired(session, caller.tenant_id, parse_id)
    if parse is None or parse.actor_user_id != caller.user_id:
        return
    company = await company_repository.get(session, caller.tenant_id, parse.company_id)
    if company is None or not learning_service.enabled(company):
        return
    stored = [draft_key(d) for d in parse.model_output.get("drafts", [])]
    used: set[int] = set()
    for position, (draft, proposal) in enumerate(zip(drafts, proposals, strict=True)):
        if proposal.company_id not in (None, parse.company_id):
            continue
        key = draft_key(draft.model_dump(mode="json", by_alias=True, exclude_none=True))
        index = next((i for i, k in enumerate(stored) if k == key and i not in used), None)
        if index is not None:
            used.add(index)
        await proposal_learning_source_repository.create(
            session,
            tenant_id=caller.tenant_id,
            proposal_id=proposal.id,
            kind=KIND_TEACH,
            draft_index=min(position, MAX_DRAFT_INDEX) if index is None else index,
            edited=index is None,
            parse_id=parse.id,
        )


async def link_stored(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company: Company,
    kind: str,
    source_id: uuid.UUID,
    indexes: list[int],
    proposal_ids: list[uuid.UUID],
) -> None:
    """Link proposals made from a stored expansion (`expand`) or extraction job
    (`extraction`) to their source, each with the index of its stored draft."""
    if not learning_service.enabled(company):
        return
    for index, proposal_id in zip(indexes, proposal_ids, strict=True):
        await proposal_learning_source_repository.create(
            session,
            tenant_id=tenant_id,
            proposal_id=proposal_id,
            kind=kind,
            draft_index=index,
            expansion_id=source_id if kind == KIND_EXPAND else None,
            job_id=source_id if kind == KIND_EXTRACTION else None,
        )


def label_before(view: OntologyView, proposal: Proposal) -> str | None:
    """The current label of the concept a rename proposal renames, read before it is applied."""
    if proposal.type is not ProposalType.CHANGE or proposal.change_kind is not ChangeKind.RENAME:
        return None
    concept = view.concepts.get(uuid.UUID(str(proposal.payload["conceptId"])))
    return concept.label if concept else None


async def on_approved(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    previous_label: str | None,
    bulk: bool,
) -> None:
    """Learn from an approval, after the proposal is applied."""
    if caller.actor_kind is not ActorKind.USER:
        return
    try:
        async with session.begin_nested():
            await _capture_approval(session, caller, view, proposal, previous_label, bulk)
    except Exception:
        logger.exception("capturing a lesson from an approval failed; the decision stands")


async def on_rejected(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal
) -> None:
    """Learn from a direct rejection: the rejected draft becomes a negative example."""
    if caller.actor_kind is not ActorKind.USER:
        return
    try:
        async with session.begin_nested():
            await _capture_rejection(session, caller, view, proposal)
    except Exception:
        logger.exception("capturing a lesson from a rejection failed; the decision stands")


async def on_concepts_removed(
    session: AsyncSession, caller: Caller, view: OntologyView, concepts: list[Concept]
) -> None:
    """Retire the lessons and aliases naming removed concepts; a lesson approved in the last 24
    hours becomes a negative, since its structure was just undone."""
    try:
        async with session.begin_nested():
            await _capture_removal(session, caller, view, concepts)
    except Exception:
        logger.exception("retiring lessons of removed concepts failed; the decision stands")


def approved_structure(view: OntologyView, proposal: Proposal) -> dict[str, Any] | None:
    """The approved proposal as a lesson structure: its labels, action, domain and values."""
    draft: dict[str, Any] | None = None
    if proposal.type in (ProposalType.CONCEPT, ProposalType.SPEC) and proposal.concept_id:
        concept = view.concepts.get(proposal.concept_id)
        parent = view.concepts.get(concept.parent_id) if concept and concept.parent_id else None
        if concept is None or parent is None:
            return None
        draft = {"type": proposal.type.value, "label": concept.label, "parent": parent.label}
        if proposal.type is ProposalType.CONCEPT:
            draft["action"] = concept.birth_action or "relates to"
            if concept.birth_reverse:
                draft["reverse"] = True
        elif concept.rule:
            draft["rule"] = concept.rule
        domain = view.domain_key(concept)
        if domain:
            draft["domain"] = domain
    elif proposal.type is ProposalType.RELATION and proposal.relation_id:
        relation = view.relations.get(proposal.relation_id)
        a = view.concepts.get(relation.a_id) if relation else None
        b = view.concepts.get(relation.b_id) if relation else None
        if relation is None or a is None or b is None:
            return None
        draft = {"type": "relation", "a": a.label, "action": relation.label, "b": b.label}
    elif proposal.type is ProposalType.ATTR:
        attribute = view.attribute(proposal.attribute_id)
        concept = view.concepts.get(attribute.concept_id) if attribute else None
        if attribute is None or concept is None or attribute.value is None:
            return None
        draft = {
            "type": "attr",
            "concept": concept.label,
            "name": attribute.name,
            "attributeType": attribute.type.value,
            "value": attribute.value,
        }
    return structure([draft]) if draft else None


async def _capture_approval(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    previous_label: str | None,
    bulk: bool,
) -> None:
    now = get_clock().now()
    company = view.companies.get(proposal.company_id) if proposal.company_id else None
    if company is None or not learning_service.enabled(company):
        return
    if proposal.type is ProposalType.CHANGE:
        if proposal.change_kind is ChangeKind.RENAME and previous_label:
            await _rename_alias(session, caller, view, company, proposal, previous_label, now)
        return
    link = await proposal_learning_source_repository.get(session, caller.tenant_id, proposal.id)
    if link is None:
        return
    source = await _source(session, view, link, proposal)
    approved = approved_structure(view, proposal)
    if source is None or approved is None or _bytes(approved) > MAX_LESSON_BYTES:
        return
    concept_ids = _concept_ids(view, proposal)
    same_source = [
        s.proposal_id
        for s in await proposal_learning_source_repository.list_same_source(session, link)
    ]
    existing = await learning_example_repository.find_active_by_proposals(
        session, caller.tenant_id, company.id, same_source, ("approve", "correct")
    )
    if existing is not None:
        combined = merged(existing.final_structure, approved)
        if _bytes(combined) <= MAX_LESSON_BYTES:
            await learning_example_repository.update_structure(
                session,
                existing,
                final_structure=combined,
                proposal_ids=_ids([*existing.proposal_ids, proposal.id]),
                concept_ids=_ids([*existing.concept_ids, *concept_ids]),
                bulk=existing.bulk and bulk,
            )
        return
    lesson = await _correction(
        session, caller, view, company, proposal, link, source, approved, concept_ids, now
    )
    if lesson is None:
        await learning_example_repository.create(
            session,
            tenant_id=caller.tenant_id,
            company_id=company.id,
            signal="approve",
            task=source.task,
            origin=source.origin,
            source_text=source.text,
            model_output=None,
            final_structure=approved,
            proposal_ids=[proposal.id],
            concept_ids=concept_ids,
            corrects_id=None,
            bulk=bulk,
            actor_user_id=caller.user_id,
        )
    await learning_example_repository.retire_over_cap(
        session, caller.tenant_id, company.id, learning_example_repository.MAX_ACTIVE, now
    )


async def _correction(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    company: Company,
    proposal: Proposal,
    link: ProposalLearningSource,
    source: _Source,
    approved: dict[str, Any],
    concept_ids: list[uuid.UUID],
    now: datetime,
) -> LearningExample | None:
    """A `correct` lesson when the approval answers an earlier rejection by the same user on
    the same subject, or approves a draft the user edited; None otherwise."""
    parse = source.parse
    if parse is None:
        return None
    produced = structure(compact(d, _label_of(view)) for d in source.drafts)
    if link.edited:
        if not produced["drafts"] or _bytes(produced) > MAX_LESSON_BYTES:
            return None
        lesson = await _create_correction(
            session, caller, company, source, produced, approved, None, proposal, concept_ids
        )
        contradicted = touched(produced) - touched(approved)
        await _supersede(session, caller.tenant_id, company.id, source.text, contradicted, now)
        if source.origin is ProposalOrigin.SPEECH:
            await _learn_aliases(session, caller, view, company, produced, approved, now)
        return lesson
    window = timedelta(minutes=get_settings().learning_correction_window_minutes)
    since = now - max(window, SESSION_LIFETIME)
    rejects = await learning_example_repository.recent_by_actor(
        session, caller.tenant_id, company.id, parse.actor_user_id, "reject", since
    )
    subject = touched(approved, ignore=[company.name])
    for reject in rejects:
        if reject.model_output is None or not (touched(reject.model_output) & subject):
            continue
        if parse.created_at < reject.created_at:
            continue
        in_window = parse.created_at - reject.created_at <= window
        if not in_window and not await _same_session(session, caller.tenant_id, reject, parse):
            continue
        lesson = await _create_correction(
            session,
            caller,
            company,
            source,
            reject.model_output,
            approved,
            reject.id,
            proposal,
            concept_ids,
        )
        contradicted = touched(reject.model_output) - touched(approved)
        await _supersede(
            session, caller.tenant_id, company.id, reject.source_text, contradicted, now
        )
        if ProposalOrigin.SPEECH in (reject.origin, source.origin):
            await _learn_aliases(session, caller, view, company, reject.model_output, approved, now)
        return lesson
    return None


async def _create_correction(
    session: AsyncSession,
    caller: Caller,
    company: Company,
    source: _Source,
    produced: dict[str, Any],
    approved: dict[str, Any],
    corrects_id: uuid.UUID | None,
    proposal: Proposal,
    concept_ids: list[uuid.UUID],
) -> LearningExample:
    return await learning_example_repository.create(
        session,
        tenant_id=caller.tenant_id,
        company_id=company.id,
        signal="correct",
        task=source.task,
        origin=source.origin,
        source_text=source.text,
        model_output=produced,
        final_structure=approved,
        proposal_ids=[proposal.id],
        concept_ids=concept_ids,
        corrects_id=corrects_id,
        bulk=False,
        actor_user_id=caller.user_id,
    )


async def _same_session(
    session: AsyncSession, tenant_id: uuid.UUID, reject: LearningExample, parse: TeachParse
) -> bool:
    """True when the rejected proposal's parse and `parse` share a teach session."""
    if parse.session_id is None or not reject.proposal_ids:
        return False
    link = await proposal_learning_source_repository.get(session, tenant_id, reject.proposal_ids[0])
    if link is None or link.parse_id is None:
        return False
    earlier = await teach_parse_repository.get(session, tenant_id, link.parse_id)
    return earlier is not None and earlier.session_id == parse.session_id


async def _supersede(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    text: str,
    contradicted: set[str],
    now: datetime,
) -> None:
    """Retire the active approvals of the source whose labels the correction contradicts:
    those naming a label the model produced and the person did not keep."""
    if not contradicted:
        return
    for lesson in await learning_example_repository.list_active_by_source(
        session, tenant_id, company_id, text, "approve"
    ):
        if touched(lesson.final_structure) & contradicted:
            await learning_example_repository.retire(session, lesson, "superseded", now)


async def _learn_aliases(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    company: Company,
    produced: dict[str, Any],
    approved: dict[str, Any],
    now: datetime,
) -> None:
    """An alias for each rejected new label that is one misheard form of an approved label."""
    names = [c.name for c in view.companies.values()]
    meant_labels = new_labels(approved)
    heard_labels = [
        label
        for label in new_labels(produced)
        if fold(label) not in {fold(m) for m in meant_labels}
    ]
    learnt = False
    for heard in heard_labels:
        for meant in meant_labels:
            if not is_alias(heard, meant, company_names=names):
                continue
            concept = view.find_label(company.id, meant)
            await company_alias_repository.create(
                session,
                tenant_id=caller.tenant_id,
                company_id=company.id,
                heard=heard,
                meant=meant,
                concept_id=concept.id if concept else None,
                actor_user_id=caller.user_id,
                at=now,
            )
            learnt = True
            break
    if learnt:
        await company_alias_repository.retire_over_cap(
            session, caller.tenant_id, company.id, company_alias_repository.MAX_ACTIVE, now
        )


async def _rename_alias(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    company: Company,
    proposal: Proposal,
    previous_label: str,
    now: datetime,
) -> None:
    """The old and new labels of a renamed concept born from speech in the last 24 hours."""
    concept = view.concepts.get(uuid.UUID(str(proposal.payload["conceptId"])))
    if concept is None:
        return
    birth = await proposal_repository.get_birth(session, caller.tenant_id, concept.id)
    if (
        birth is None
        or birth.origin is not ProposalOrigin.SPEECH
        or birth.decided_at is None
        or now - birth.decided_at > RECENT_APPROVAL
    ):
        return
    heard, meant = previous_label, concept.label
    if not storable(heard) or not storable(meant) or fold(heard) == fold(meant):
        return
    await company_alias_repository.create(
        session,
        tenant_id=caller.tenant_id,
        company_id=company.id,
        heard=heard,
        meant=meant,
        concept_id=concept.id,
        actor_user_id=caller.user_id,
        at=now,
    )
    await company_alias_repository.retire_over_cap(
        session, caller.tenant_id, company.id, company_alias_repository.MAX_ACTIVE, now
    )


async def _capture_rejection(
    session: AsyncSession, caller: Caller, view: OntologyView, proposal: Proposal
) -> None:
    company = view.companies.get(proposal.company_id) if proposal.company_id else None
    if company is None or not learning_service.enabled(company):
        return
    link = await proposal_learning_source_repository.get(session, caller.tenant_id, proposal.id)
    if link is None or link.edited:
        return
    source = await _source(session, view, link, proposal)
    if source is None or link.draft_index >= len(source.drafts):
        return
    produced = structure([compact(source.drafts[link.draft_index], _label_of(view))])
    if not produced["drafts"] or _bytes(produced) > MAX_LESSON_BYTES:
        return
    await learning_example_repository.create(
        session,
        tenant_id=caller.tenant_id,
        company_id=company.id,
        signal="reject",
        task=source.task,
        origin=source.origin,
        source_text=source.text,
        model_output=produced,
        final_structure=None,
        proposal_ids=[proposal.id],
        concept_ids=[],
        corrects_id=None,
        bulk=False,
        actor_user_id=caller.user_id,
    )
    await learning_example_repository.retire_over_cap(
        session,
        caller.tenant_id,
        company.id,
        learning_example_repository.MAX_ACTIVE,
        get_clock().now(),
    )


async def _capture_removal(
    session: AsyncSession, caller: Caller, view: OntologyView, concepts: list[Concept]
) -> None:
    now = get_clock().now()
    ids = [c.id for c in concepts]
    retired = await learning_example_repository.retire_by_concepts(
        session, caller.tenant_id, ids, now
    )
    await company_alias_repository.retire_by_concepts(session, caller.tenant_id, ids, now)
    if caller.actor_kind is not ActorKind.USER:
        return
    for lesson in retired:
        company = view.companies.get(lesson.company_id)
        if company is None or not learning_service.enabled(company):
            continue
        if lesson.signal == "reject" or lesson.final_structure is None:
            continue
        if now - lesson.created_at > RECENT_APPROVAL:
            continue
        await learning_example_repository.create(
            session,
            tenant_id=caller.tenant_id,
            company_id=company.id,
            signal="reject",
            task=lesson.task,
            origin=lesson.origin,
            source_text=lesson.source_text,
            model_output=lesson.final_structure,
            final_structure=None,
            proposal_ids=list(lesson.proposal_ids),
            concept_ids=[],
            corrects_id=None,
            bulk=False,
            actor_user_id=caller.user_id,
        )


async def _source(
    session: AsyncSession, view: OntologyView, link: ProposalLearningSource, proposal: Proposal
) -> _Source | None:
    tenant_id = link.tenant_id
    if link.kind == KIND_TEACH and link.parse_id is not None:
        parse = await teach_parse_repository.get(session, tenant_id, link.parse_id)
        if parse is None:
            return None
        drafts = list(parse.model_output.get("drafts", []))
        return _Source(parse.source_text, parse.origin, KIND_TEACH, drafts, parse)
    if link.kind == KIND_EXPAND and link.expansion_id is not None:
        row = await concept_expansion_repository.get(session, tenant_id, link.expansion_id)
        if row is None:
            return None
        concept = view.concepts.get(row.concept_id)
        text = f"Expand {concept.label if concept else proposal.title}"
        return _Source(text, ProposalOrigin.SUGGESTION, KIND_EXPAND, list(row.drafts), None)
    if link.kind == KIND_EXTRACTION and link.job_id is not None:
        job = await document_extraction_job_repository.get(session, tenant_id, link.job_id)
        if job is None:
            return None
        text = await _extraction_sentence(session, tenant_id, job, link.draft_index)
        drafts = list(job.drafts or [])
        origin = ProposalOrigin.DOCUMENT
        return _Source(text or proposal.title, origin, KIND_EXTRACTION, drafts, None)
    return None


async def _extraction_sentence(
    session: AsyncSession, tenant_id: uuid.UUID, job: Any, draft_index: int
) -> str | None:
    """The document sentence a stored extraction draft was grounded in, while its import is
    still stored."""
    notes = job.notes or []
    if job.import_id is None or draft_index >= len(notes):
        return None
    index = notes[draft_index].get("sentenceIndex")
    if index is None:
        return None
    texts = await document_import_sentence_repository.texts_between(
        session, tenant_id, job.import_id, int(index), int(index) + 1
    )
    text = (texts.get(int(index)) or "").strip()
    return text[:MAX_SOURCE_CHARS] or None


def _concept_ids(view: OntologyView, proposal: Proposal) -> list[uuid.UUID]:
    """The approved concepts a lesson names, so that deleting one retires it."""
    if proposal.type in (ProposalType.CONCEPT, ProposalType.SPEC) and proposal.concept_id:
        return [proposal.concept_id]
    if proposal.type is ProposalType.RELATION and proposal.relation_id:
        relation = view.relations.get(proposal.relation_id)
        return [relation.a_id, relation.b_id] if relation else []
    if proposal.type is ProposalType.ATTR:
        attribute = view.attribute(proposal.attribute_id)
        return [attribute.concept_id] if attribute else []
    return []


def _label_of(view: OntologyView) -> LabelOf:
    def label_of(concept_id: str) -> str | None:
        try:
            concept = view.concepts.get(uuid.UUID(concept_id))
        except ValueError:
            return None
        return concept.label if concept else None

    return label_of


def _ids(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    return list(dict.fromkeys(ids))[:MAX_IDS]


def _bytes(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
