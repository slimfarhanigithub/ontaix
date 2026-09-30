"""Concept expansion: the model suggests a mind-map branch under one concept, as drafts only.

In order: the concept must be readable, approved and live (or the company root), the caller
must hold `proposal.create` in its scope through Owner or Builder, and one unit of the caller's
hourly `expand` budget is spent. The request's transaction then ends, so no lock is held during
the model call. A provider must be configured and the tenant's monthly token cap above 0; one
unit of the hourly `llm` budget is spent and the call's upper bound is reserved against the cap.
The model receives, as data, only the expanded concept (handle `e0`), its ancestors, siblings
and descendants, the company's labels in its domain, the company name, the domain templates and
the caller's steering. The reservation is settled and one cost record stored whatever happens.
A valid answer is checked, trimmed to the configured ceiling and mapped to drafts in
breadth-first order; the drafts are stored for one hour so that a selection of them can be
proposed with origin `suggestion`. Nothing here writes an ontology row or a proposal.
"""

from __future__ import annotations

import json
import logging
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.concept_expansion import OUTPUT_SCHEMA, OUTPUT_TOKENS_PER_DRAFT, SYSTEM_PROMPT
from app.auth import Caller
from app.clients.db_client import get_session_factory
from app.clients.llm_client import (
    LlmCallError,
    LlmRefused,
    LlmRequest,
    LlmTimeout,
    get_llm_client,
)
from app.config import LlmProfile, get_settings
from app.models.api.expansion import (
    ExpansionNote,
    ExpansionOutcome,
    ExpansionRequest,
    ExpansionResult,
    ExpansionSkip,
)
from app.models.api.settings import DEFAULT_LLM_MONTHLY_TOKEN_CAP
from app.models.llm.concept_expansion_answer import ConceptExpansionAnswer, Suggestion
from app.models.storage.base import NodeKind
from app.models.storage.concept import Concept
from app.repositories import concept_expansion_repository
from app.repositories.llm_call_repository import CallRecord
from app.services import learning_service, llm_usage_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import Budget, charge, try_charge
from app.utilities.action_text import has_refused_character, normalise_action
from app.utilities.clock import get_clock
from app.utilities.permissions import Scope, can_propose_as_builder, can_read
from app.utilities.problems import conflict, forbidden, not_found
from app.utilities.teach_parser import singular, title

logger = logging.getLogger(__name__)

DEEP: LlmProfile = "deep"


ROOT_HANDLE = "e0"
MIN_CONFIDENCE = 0.4
DEFAULT_DOMAIN = "production"
REFUSED_ACTIONS = frozenset({"is a", "equivalent to"})
MAX_SKIP_LABEL = 130
PURGE_AFTER_EXPIRY = timedelta(hours=24)


@dataclass
class _Kept:
    suggestion: Suggestion
    label: str
    depth: int
    domain: str


@dataclass
class _Interpretation:
    drafts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[ExpansionNote] = field(default_factory=list)
    skipped: list[ExpansionSkip] = field(default_factory=list)


class _InvalidAnswer(Exception):
    """The answer failed the schema or a check the schema cannot express."""


async def expand(
    session: AsyncSession, caller: Caller, concept_id: uuid.UUID, body: ExpansionRequest
) -> ExpansionResult:
    view = await load_view(session, caller.tenant_id)
    concept = _expandable(caller, view, concept_id)
    await charge(Budget.EXPAND, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    # The request's own transaction ends here, so it holds no lock during the model call.
    await session.commit()
    outcome, interpretation = await _suggest(caller, view, concept, body)
    if outcome != "used":
        return _degraded(concept.id, outcome)
    assert interpretation is not None
    expansion_id = expires_at = None
    if interpretation.drafts:
        async with get_session_factory()() as write:
            row = await concept_expansion_repository.create(
                write,
                tenant_id=caller.tenant_id,
                actor_user_id=caller.user_id,
                company_id=concept.company_id,
                concept_id=concept.id,
                session_id=body.session_id,
                depth=body.depth,
                max_children=body.max_children,
                drafts=interpretation.drafts,
                notes=[n.model_dump(mode="json", by_alias=True) for n in interpretation.notes],
            )
            await write.commit()
        expansion_id, expires_at = row.id, row.expires_at
    return ExpansionResult(
        expansion_id=expansion_id,
        expires_at=expires_at,
        concept_id=concept.id,
        llm_outcome="used",
        degraded=False,
        drafts=interpretation.drafts,
        notes=interpretation.notes,
        skipped=interpretation.skipped,
    )


async def purge_expired() -> int:
    """Delete expansions more than 24 hours past their expiry, in their own transaction."""
    async with get_session_factory()() as session:
        deleted = await concept_expansion_repository.delete_expired_before(
            session, get_clock().now() - PURGE_AFTER_EXPIRY
        )
        await session.commit()
    return deleted


def expansion_scope(view: OntologyView, concept: Concept) -> Scope:
    return Scope(concept.company_id, view.domain_key(concept))


def _expandable(caller: Caller, view: OntologyView, concept_id: uuid.UUID) -> Concept:
    """The concept, readable, approved and live, or the company root; the caller's right to
    expand it is checked before its state."""
    concept = view.concepts.get(concept_id)
    if concept is None or concept.dying_at is not None:
        raise not_found("concept")
    company = view.companies.get(concept.company_id)
    if company is None or company.dying_at is not None or not can_read(caller.grants, company.id):
        raise not_found("concept")
    if not can_propose_as_builder(caller.grants, expansion_scope(view, concept)):
        raise forbidden("Expanding a concept needs the Owner or Builder role in its scope")
    if concept.pending and concept.kind is not NodeKind.ROOT:
        raise conflict("concept_pending", f"{concept.label} is awaiting approval")
    return concept


async def _suggest(
    caller: Caller, view: OntologyView, concept: Concept, body: ExpansionRequest
) -> tuple[ExpansionOutcome, _Interpretation | None]:
    try:
        return await _call(caller, view, concept, body)
    except Exception:
        logger.exception("the concept expansion step failed")
        return "provider_error", None


async def _call(
    caller: Caller, view: OntologyView, concept: Concept, body: ExpansionRequest
) -> tuple[ExpansionOutcome, _Interpretation | None]:
    client = get_llm_client(DEEP)
    if client is None:
        return "not_configured", None
    cap = view.settings.llm_monthly_token_cap if view.settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
    if cap <= 0:
        return "budget_exhausted", None
    actor_kind = caller.actor_kind.value
    if not await try_charge(Budget.LLM, caller.tenant_id, actor_kind, caller.user_id):
        return "rate_limited", None
    config = get_settings()
    answer_bound = min(
        OUTPUT_TOKENS_PER_DRAFT * config.expand_max_nodes, config.expand_max_output_tokens
    )
    learning = await learning_service.context_for(
        view, concept.company_id, f"Expand {concept.label} {body.focus or ''}".strip(), "expand"
    )
    request = LlmRequest(
        system=SYSTEM_PROMPT,
        user=_context(
            view,
            concept,
            body,
            config.expand_context_labels,
            learning.as_data() if learning else {},
        ),
        output_schema=OUTPUT_SCHEMA,
        max_output_tokens=answer_bound + config.llm_profile(DEEP).reasoning_allowance_tokens,
        timeout_seconds=config.expand_timeout_seconds,
    )
    upper_bound = client.estimate_input_tokens(request) + request.max_output_tokens
    reservation = await llm_usage_service.reserve(caller.tenant_id, upper_bound, cap)
    if reservation is None:
        return "budget_exhausted", None

    # Whatever happens from here on, the reservation is settled and one cost row is written.
    outcome: ExpansionOutcome = "invalid_output"
    usage = (0, 0, 0.0, 0)
    try:
        try:
            answer = await client.complete(request)
        except LlmCallError as exc:
            usage = (exc.input_tokens, exc.output_tokens, exc.cost_eur, exc.latency_ms)
            if isinstance(exc, LlmTimeout):
                outcome = "timeout"
            elif isinstance(exc, LlmRefused):
                outcome = "refused"
            else:
                outcome = "provider_error"
            return outcome, None
        except Exception:
            logger.exception("the language model adapter failed unexpectedly")
            outcome = "provider_error"
            return outcome, None
        usage = (answer.input_tokens, answer.output_tokens, answer.cost_eur, answer.latency_ms)
        try:
            interpretation = _interpret(answer.text, view, concept, body, config.expand_max_nodes)
        except _InvalidAnswer as exc:
            logger.info("the concept expansion answer was refused: %s", exc)
            return "invalid_output", None
        outcome = "used"
        return outcome, interpretation
    finally:
        record = CallRecord(
            tenant_id=caller.tenant_id,
            actor_kind=actor_kind,
            actor_id=caller.user_id,
            company_id=concept.company_id,
            purpose=llm_usage_service.CONCEPT_EXPANSION,
            provider=client.provider,
            model=client.model,
            input_tokens=usage[0],
            output_tokens=usage[1],
            cost_eur=usage[2],
            latency_ms=usage[3],
            outcome=outcome,
        )
        try:
            await llm_usage_service.settle(reservation, record)
        except Exception:
            logger.exception("settling a language model call failed; its reservation stays")


def _context(
    view: OntologyView,
    concept: Concept,
    body: ExpansionRequest,
    budget: int,
    learning: dict[str, Any] | None = None,
) -> str:
    """The user message: the call's data as JSON, labels only, nearest to e0 first; the
    company's learning (`learning`, as data fields) comes last."""
    company = view.companies[concept.company_id]
    is_root = concept.kind is NodeKind.ROOT
    remaining = budget

    def take(labels: list[Any]) -> list[Any]:
        nonlocal remaining
        kept = labels[: max(remaining, 0)]
        remaining -= len(kept)
        return kept

    ancestors = take([a.label for a in view.ancestors_of(concept.id)])
    descendants = take(
        [
            {"label": c.label, "depth": depth, "parent": parent_label}
            for c, depth, parent_label in _descendants(view, concept)
        ]
    )
    parent = view.concepts.get(concept.parent_id) if concept.parent_id else None
    siblings = take(
        [c.label for c in view.children_of(parent.id) if c.id != concept.id] if parent else []
    )
    shown = {concept.id, *(c.id for c, _, _ in _descendants(view, concept))}
    if parent is not None:
        shown.update(c.id for c in view.children_of(parent.id))
    if is_root:
        pool = [c for c in view.children_of(concept.id) if c.id not in shown]
    else:
        key = view.domain_key(concept)
        pool = [
            c
            for c in view.live_concepts()
            if c.company_id == concept.company_id
            and c.id not in shown
            and c.kind is NodeKind.CONCEPT
            and view.domain_key(c) == key
        ]
    pool.sort(key=lambda c: (c.born_at, str(c.id)), reverse=True)
    domain_labels = take([c.label for c in pool])
    data: dict[str, Any] = {
        "company": company.name,
        "expanded": {
            "handle": ROOT_HANDLE,
            "label": concept.label,
            "domain": view.domain_key(concept),
            "isRoot": is_root,
        },
        "ancestors": ancestors,
        "siblings": siblings,
        "descendants": descendants,
        "domainLabels": domain_labels,
        "domainTemplates": [
            {"key": key, "name": t.name}
            for key, t in sorted(view.templates.items(), key=lambda kv: kv[1].position)
        ],
        "focus": body.focus,
        "depth": body.depth,
        "maxChildren": body.max_children,
    }
    data.update(learning or {})
    return json.dumps(data, ensure_ascii=False)


def _descendants(view: OntologyView, concept: Concept) -> list[tuple[Concept, int, str]]:
    """Live and pending descendants breadth-first, each with its depth and parent label."""
    out: list[tuple[Concept, int, str]] = []
    seen = {concept.id}
    queue: deque[tuple[Concept, int]] = deque([(concept, 0)])
    while queue:
        current, depth = queue.popleft()
        for child in sorted(view.children_of(current.id), key=lambda c: (c.born_at, str(c.id))):
            if child.id in seen:
                continue
            seen.add(child.id)
            out.append((child, depth + 1, current.label))
            queue.append((child, depth + 1))
    return out


def _interpret(
    raw: str, view: OntologyView, concept: Concept, body: ExpansionRequest, ceiling: int
) -> _Interpretation:
    """Validates the whole answer, then drops what the rules drop and maps the rest."""
    try:
        answer = ConceptExpansionAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise _InvalidAnswer(f"{exc.error_count()} schema errors") from None
    keys: set[str] = set()
    for s in answer.suggestions:
        if s.key in keys:
            raise _InvalidAnswer("a key repeats")
        if s.parent != ROOT_HANDLE and s.parent not in keys:
            raise _InvalidAnswer("a parent is neither e0 nor an earlier key")
        keys.add(s.key)
        _check_text(s.label, s.action, s.rationale)
    for link in answer.links:
        if link.from_ == link.to:
            raise _InvalidAnswer("a link joins a concept to itself")
        if any(end != ROOT_HANDLE and end not in keys for end in (link.from_, link.to)):
            raise _InvalidAnswer("a link names a key the answer does not hold")
        _check_text(None, link.action, link.rationale)

    existing = {
        _label_key(c.label)
        for c in view.live_concepts()
        if c.company_id == concept.company_id and c.kind is NodeKind.CONCEPT
    }
    existing.add(_label_key(concept.label))
    is_root = concept.kind is NodeKind.ROOT
    root_domain = view.domain_key(concept)
    out = _Interpretation()
    kept: dict[str, _Kept] = {}
    skipped: set[str] = set()
    labels_seen: set[str] = set()
    children: dict[str, int] = {}
    total = 0

    def skip(key: str, label: str, reason: str) -> None:
        skipped.add(key)
        out.skipped.append(ExpansionSkip(label=label[:MAX_SKIP_LABEL], reason=reason))

    labels = {s.key: title(unicodedata.normalize("NFKC", s.label)) for s in answer.suggestions}
    for s in answer.suggestions:
        label = labels[s.key]
        if s.parent in skipped:
            skip(s.key, label, "parent_skipped")
            continue
        # Every earlier key is kept or skipped, so a parent that is not skipped is kept.
        depth = 1 if s.parent == ROOT_HANDLE else kept[s.parent].depth + 1
        if s.confidence < MIN_CONFIDENCE:
            skip(s.key, label, "low_confidence")
            continue
        key = _label_key(label)
        if key in existing:
            skip(s.key, label, "existing_label")
            continue
        if key in labels_seen:
            skip(s.key, label, "duplicate_in_response")
            continue
        too_deep = body.depth is not None and depth > body.depth
        too_many = body.max_children is not None and children.get(s.parent, 0) >= body.max_children
        if too_deep or too_many or total >= ceiling:
            skip(s.key, label, "over_cap")
            continue
        if s.parent == ROOT_HANDLE:
            domain = (s.domain_key or DEFAULT_DOMAIN) if is_root else root_domain or DEFAULT_DOMAIN
        else:
            domain = kept[s.parent].domain
        kept[s.key] = _Kept(s, label, depth, domain)
        labels_seen.add(key)
        children[s.parent] = children.get(s.parent, 0) + 1
        total += 1

    order = sorted(kept.values(), key=lambda k: k.depth)
    index_of: dict[str, int] = {}
    company = str(concept.company_id)
    for k in order:
        s = k.suggestion
        draft: dict[str, Any] = {"type": "concept", "companyId": company}
        if s.parent == ROOT_HANDLE:
            draft["parentId"] = str(concept.id)
        else:
            draft["parentLabel"] = kept[s.parent].label
        draft.update(
            label=k.label, domainKey=k.domain, action=normalise_action(s.action), reverse=False
        )
        index_of[s.key] = len(out.drafts)
        out.drafts.append(draft)
        requires = [] if s.parent == ROOT_HANDLE else [index_of[s.parent]]
        out.notes.append(
            ExpansionNote(
                confidence=s.confidence, rationale=s.rationale, depth=k.depth, requires=requires
            )
        )

    births = {(k.suggestion.parent, key) for key, k in kept.items()}
    links_seen: set[tuple[str, str, str]] = set()

    def name(handle: str) -> str:
        return concept.label if handle == ROOT_HANDLE else labels[handle]

    for link in answer.links:
        action = normalise_action(link.action)
        text = f"{name(link.from_)} {action} {name(link.to)}"
        if link.from_ in skipped or link.to in skipped:
            out.skipped.append(ExpansionSkip(label=text[:MAX_SKIP_LABEL], reason="parent_skipped"))
            continue
        if link.confidence < MIN_CONFIDENCE:
            out.skipped.append(ExpansionSkip(label=text[:MAX_SKIP_LABEL], reason="low_confidence"))
            continue
        pair = {(link.from_, link.to), (link.to, link.from_)}
        if pair & births or (link.from_, action, link.to) in links_seen:
            out.skipped.append(
                ExpansionSkip(label=text[:MAX_SKIP_LABEL], reason="duplicate_relation")
            )
            continue
        if total >= ceiling:
            out.skipped.append(ExpansionSkip(label=text[:MAX_SKIP_LABEL], reason="over_cap"))
            continue
        links_seen.add((link.from_, action, link.to))
        total += 1
        draft = {"type": "relation", "companyId": company, "action": action}
        requires = []
        for side, handle in (("a", link.from_), ("b", link.to)):
            if handle == ROOT_HANDLE:
                draft[f"{side}Id"] = str(concept.id)
            else:
                draft[f"{side}Label"] = kept[handle].label
                requires.append(index_of[handle])
        out.drafts.append(draft)
        out.notes.append(
            ExpansionNote(
                confidence=link.confidence,
                rationale=link.rationale,
                depth=None,
                requires=list(dict.fromkeys(requires)),
            )
        )
    return out


def _check_text(label: str | None, action: str, rationale: str) -> None:
    for text in (label, action, rationale):
        if text is not None and has_refused_character(text):
            raise _InvalidAnswer("a text holds a refused character")
    if normalise_action(action) in REFUSED_ACTIONS or not normalise_action(action):
        raise _InvalidAnswer("an action is is a or equivalent to")
    if label is not None and not any(c.isalpha() for c in unicodedata.normalize("NFKC", label)):
        raise _InvalidAnswer("a label holds no letter")


def _label_key(label: str) -> str:
    """Labels compare case-insensitively, singular or plural."""
    return singular(unicodedata.normalize("NFKC", label).strip().lower())


def _degraded(concept_id: uuid.UUID, outcome: ExpansionOutcome) -> ExpansionResult:
    return ExpansionResult(
        expansion_id=None,
        expires_at=None,
        concept_id=concept_id,
        llm_outcome=outcome,
        degraded=True,
        drafts=[],
        notes=[],
        skipped=[],
    )
