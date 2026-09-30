"""Usage learning as the model and the administrators see it.

Retrieval: for a model call in one company, the company's own lessons ranked by BM25 against the
call's text (corrections first, then individual approvals, then bulk ones) within a token budget,
up to three negatives, the aliases whose heard form occurs in the text, and a habits summary.
Only the company's rows are ever read; the switch (`ONTAIX_LEARNING_ENABLED` and the company's
`learning` column) turns it all off. Reading never fails a model call.

Administration: the listing, the switch, one deletion and the reset, all Administrator at tenant
scope and audited as kind `learning`. Purge: expired teach parse records and rows retired for
more than 30 days.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.clients.db_client import get_session_factory
from app.clients.llm_client import LlmRequest, estimate_tokens
from app.config import get_settings
from app.models.api.learning import (
    CompanyAlias as CompanyAliasDto,
)
from app.models.api.learning import (
    CompanyLearning,
    LearningHabits,
    LearningReset,
    LearningResetResult,
    LearningSwitched,
    LearningVerb,
    Lesson,
)
from app.models.storage.base import NodeKind, RelationKind
from app.models.storage.company import Company
from app.models.storage.company_alias import CompanyAlias
from app.models.storage.learning_example import LearningExample
from app.repositories import (
    company_alias_repository,
    company_repository,
    learning_example_repository,
    teach_parse_repository,
)
from app.services import audit_service
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities import learning_habits
from app.utilities.clock import get_clock
from app.utilities.example_selection import most_similar, within_budget
from app.utilities.learning_structure import ranked_text, words_occur
from app.utilities.lesson_selection import TIER_APPROVE, TIER_BULK, TIER_CORRECT, select
from app.utilities.listing import ListQuery, paginate
from app.utilities.permissions import can_manage
from app.utilities.problems import ProblemError, forbidden, not_found

logger = logging.getLogger(__name__)

AUDIT_KIND = "learning"
FILTERABLE = ("signal", "task")
SORTABLE = ("createdAt",)
MAX_LESSONS = 20
MAX_NEGATIVES = 3
MAX_ALIASES = 50
RETIRED_RETENTION = timedelta(days=30)
RESET_WORD = "reset"


@dataclass(frozen=True)
class LearningContext:
    """What one model call receives from the company's learning, ready as data fields."""

    lessons: list[dict[str, Any]] = field(default_factory=list)
    negatives: list[dict[str, Any]] = field(default_factory=list)
    # (heard, meant) of every active alias whose heard form occurs in the call's text.
    aliases: list[tuple[str, str]] = field(default_factory=list)
    habits: str = ""

    def as_data(self) -> dict[str, Any]:
        """The non-empty parts as JSON data fields for the user message."""
        data: dict[str, Any] = {}
        if self.lessons:
            data["companyLessons"] = self.lessons
        if self.negatives:
            data["companyNegatives"] = self.negatives
        if self.aliases:
            data["companyAliases"] = [{"heard": h, "meant": m} for h, m in self.aliases]
        if self.habits:
            data["companyHabits"] = self.habits
        return data


def enabled(company: Company) -> bool:
    """True when learning is on for the deployment and for the company."""
    return get_settings().learning_enabled and company.learning


async def context_for(
    view: OntologyView, company_id: uuid.UUID, text: str, task: str
) -> LearningContext | None:
    """The company's learning for one call about `text`, or None when learning is off or the
    company's rows could not be read. Runs in a short transaction of its own."""
    company = view.companies.get(company_id)
    if company is None or not enabled(company):
        return None
    try:
        async with get_session_factory()() as session:
            lessons = await learning_example_repository.list_active(
                session, view.tenant_id, company_id
            )
            aliases = await company_alias_repository.list_active(
                session, view.tenant_id, company_id
            )
            matched = [a for a in aliases if words_occur(a.heard, text)][:MAX_ALIASES]
            await company_alias_repository.add_hits(
                session, view.tenant_id, [a.id for a in matched]
            )
            await session.commit()
    except Exception:
        logger.warning("reading a company's lessons failed; the %s call runs without them", task)
        return None
    verbs, naming = habits_for(view, company_id)
    return build_context(text, lessons, matched, learning_habits.summary(verbs, naming))


def build_context(
    text: str, lessons: list[LearningExample], aliases: list[CompanyAlias], habits: str
) -> LearningContext:
    """Pure selection over already loaded rows: the ranked lessons within the token budget, the
    negatives within what is left, the aliases and the habits."""
    budget = get_settings().learning_context_tokens
    positives = [lesson for lesson in lessons if lesson.signal in ("approve", "correct")]
    shown = [_shown(lesson) for lesson in positives]
    costs = [_tokens(s) for s in shown]
    tiers = [_tier(lesson) for lesson in positives]
    texts = [ranked_text(lesson.source_text, lesson.final_structure) for lesson in positives]
    chosen = select(text, texts, tiers, costs, MAX_LESSONS, budget)
    spent = sum(costs[i] for i in chosen)
    rejects = [lesson for lesson in lessons if lesson.signal == "reject"]
    shown_rejects = [_shown(lesson) for lesson in rejects]
    reject_costs = [_tokens(s) for s in shown_rejects]
    ranked = most_similar(
        text, [ranked_text(lesson.source_text, lesson.model_output) for lesson in rejects]
    )
    negatives = within_budget(ranked, reject_costs, MAX_NEGATIVES, max(budget - spent, 0))
    return LearningContext(
        lessons=[shown[i] for i in chosen],
        negatives=[shown_rejects[i] for i in negatives],
        aliases=[(a.heard, a.meant) for a in aliases],
        habits=habits,
    )


def habits_for(
    view: OntologyView, company_id: uuid.UUID
) -> tuple[list[tuple[str, int]], list[str]]:
    """The company's most used actions and naming patterns, from its approved rows."""
    concepts = {
        c.id: c
        for c in view.live_concepts()
        if c.company_id == company_id and not c.pending and c.kind is NodeKind.CONCEPT
    }
    root = view.root_of(company_id)
    company_ids = set(concepts) | ({root.id} if root else set())
    actions = [
        r.label
        for r in view.live_relations()
        if r.kind is RelationKind.REL and not r.pending and r.a_id in company_ids
    ]
    labels = [c.label for c in concepts.values()]
    return learning_habits.verbs(actions), learning_habits.naming(labels)


async def list_learning(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID, query: ListQuery
) -> CompanyLearning:
    company = await _managed_company(session, caller, company_id)
    rows = await learning_example_repository.list_for_company(session, caller.tenant_id, company.id)
    signals = query.filters.get("signal")
    tasks = query.filters.get("task")
    rows = [
        r
        for r in rows
        if (signals is None or r.signal in signals) and (tasks is None or r.task in tasks)
    ]
    page, total = paginate(rows, query, {"createdAt": lambda r: r.created_at}, "createdAt")
    aliases = await company_alias_repository.list_for_company(session, caller.tenant_id, company.id)
    view = await load_view(session, caller.tenant_id)
    verbs, naming = habits_for(view, company.id)
    return CompanyLearning(
        company_id=company.id,
        enabled=company.learning,
        page=query.page,
        page_size=query.page_size,
        total=total,
        lessons=[_lesson_dto(r) for r in page],
        aliases=[_alias_dto(a) for a in aliases[: company_alias_repository.MAX_ACTIVE]],
        habits=LearningHabits(
            verbs=[LearningVerb(action=a, count=n) for a, n in verbs], naming=naming
        ),
    )


async def set_switch(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID, on: bool
) -> LearningSwitched:
    company = await _managed_company(session, caller, company_id)
    company.learning = on
    await session.flush()
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        f"Learning {'enabled' if on else 'disabled'} for {company.name}",
        True,
        company_ids=[company.id],
    )
    return LearningSwitched(company_id=company.id, enabled=on)


async def delete_lesson(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID, lesson_id: uuid.UUID
) -> None:
    """Delete one lesson or one alias of the company, active or retired."""
    company = await _managed_company(session, caller, company_id)
    lesson = await learning_example_repository.get(session, caller.tenant_id, company.id, lesson_id)
    if lesson is not None:
        await learning_example_repository.delete(session, lesson)
    else:
        alias = await company_alias_repository.get(session, caller.tenant_id, company.id, lesson_id)
        if alias is None:
            raise not_found("lesson")
        await company_alias_repository.delete(session, alias)
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        "Lesson deleted",
        True,
        company_ids=[company.id],
    )


async def reset(
    session: AsyncSession, caller: Caller, company_id: uuid.UUID, body: LearningReset
) -> LearningResetResult:
    """Delete every lesson, alias and pending teach parse record of the company."""
    company = await _managed_company(session, caller, company_id)
    if body.confirm is None:
        raise ProblemError(422, "confirmation_required", f"confirm must read {RESET_WORD}")
    if body.confirm != RESET_WORD:
        raise ProblemError(422, "confirmation_mismatch", f"confirm must read {RESET_WORD}")
    lessons = await learning_example_repository.delete_for_company(
        session, caller.tenant_id, company.id
    )
    aliases = await company_alias_repository.delete_for_company(
        session, caller.tenant_id, company.id
    )
    await teach_parse_repository.delete_for_company(session, caller.tenant_id, company.id)
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        f"Learning reset for {company.name} - {lessons} lessons, {aliases} aliases",
        True,
        company_ids=[company.id],
    )
    return LearningResetResult(lessons=lessons, aliases=aliases)


async def purge_expired() -> tuple[int, int]:
    """Delete expired teach parse records and rows retired more than 30 days ago, in their own
    transaction; returns the two counts."""
    async with get_session_factory()() as session:
        parses = await teach_parse_repository.delete_expired(session)
        cutoff = get_clock().now() - RETIRED_RETENTION
        retired = await learning_example_repository.delete_retired_before(session, cutoff)
        retired += await company_alias_repository.delete_retired_before(session, cutoff)
        await session.commit()
    return parses, retired


async def _managed_company(session: AsyncSession, caller: Caller, company_id: uuid.UUID) -> Company:
    if not can_manage(caller.grants):
        raise forbidden("Managing learning requires Administrator")
    company = await company_repository.get(session, caller.tenant_id, company_id)
    if company is None or company.dying_at is not None:
        raise not_found("company")
    return company


def _tier(lesson: LearningExample) -> int:
    if lesson.signal == "correct":
        return TIER_CORRECT
    return TIER_BULK if lesson.bulk else TIER_APPROVE


def _shown(lesson: LearningExample) -> dict[str, Any]:
    """A lesson as the model reads it: the sentence and label-only structures."""
    if lesson.signal == "reject":
        return {"input": lesson.source_text, "rejected": _drafts(lesson.model_output)}
    if lesson.signal == "correct":
        return {
            "input": lesson.source_text,
            "modelProduced": _drafts(lesson.model_output),
            "personMeant": _drafts(lesson.final_structure),
        }
    return {"input": lesson.source_text, "approved": _drafts(lesson.final_structure)}


def _drafts(struct: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((struct or {}).get("drafts", []))


def _tokens(shown: dict[str, Any]) -> int:
    return estimate_tokens(LlmRequest("", json.dumps(shown, ensure_ascii=False), {}, 0, 0))


def _lesson_dto(row: LearningExample) -> Lesson:
    return Lesson(
        id=row.id,
        signal=row.signal,
        task=row.task,
        origin=row.origin.value,
        source_text=row.source_text,
        model_output=row.model_output,
        final_structure=row.final_structure,
        corrects_id=row.corrects_id,
        bulk=row.bulk,
        proposal_ids=list(row.proposal_ids),
        created_at=row.created_at,
        retired_at=row.retired_at,
        retired_reason=row.retired_reason,
    )


def _alias_dto(row: CompanyAlias) -> CompanyAliasDto:
    return CompanyAliasDto(
        id=row.id,
        heard=row.heard,
        meant=row.meant,
        concept_id=row.concept_id,
        hits=row.hits,
        created_at=row.created_at,
        retired_at=row.retired_at,
    )
