"""The language model step of a teach parse: context, budgets, the call, validation, mapping.

The step runs behind the grammar, only when a fallback trigger holds. In order: a provider must
be configured and the tenant's monthly token cap above 0; the caller's hourly `llm` budget is
charged; the call's upper bound is reserved against the monthly cap and committed; the adapter
calls the model with nothing but the sentence, the session's recent turns, the company name, up
to 200 candidate concepts as per-call handles (`c0` is the company root), the domain templates
and the action guidance. The reservation is settled and a cost record stored whatever happens.
A valid answer is mapped to drafts with the grammar's mapping; anything else leaves the
grammar's result standing and the step reports why. The step never raises.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.ai.prompts.teach_extraction import (
    MAX_OUTPUT_TOKENS,
    OUTPUT_SCHEMA,
    SPEECH_MAX_OUTPUT_TOKENS,
    SYSTEM_PROMPT,
)
from app.auth import Caller
from app.clients.llm_client import (
    LlmCallError,
    LlmRequest,
    LlmTimeout,
    get_llm_client,
)
from app.config import get_settings
from app.models.api.settings import DEFAULT_LLM_MONTHLY_TOKEN_CAP
from app.models.api.teach import DraftNote, LlmOutcome, SourceSpan, UnresolvedPhrase
from app.models.llm.teach_extraction_answer import (
    AnswerIntent,
    CandidateRef,
    TeachExtractionAnswer,
)
from app.models.storage.concept import Concept
from app.repositories.llm_call_repository import CallRecord
from app.repositories.teach_session_turn_repository import StoredTurn
from app.services import llm_usage_service
from app.services.ontology_view_service import OntologyView
from app.services.rate_limit_service import Budget, try_charge
from app.services.teach_draft_service import Drafter, End, PlannedIntent, phrase_in
from app.utilities.action_text import has_refused_character, normalise_action
from app.utilities.permissions import can_read
from app.utilities.teach_parser import singular, title

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 200
MAX_OTHER_COMPANY_CANDIDATES = 50
MIN_CONFIDENCE = 0.4
MAX_SENTENCE_INTENTS = 20
MAX_SENTENCE_PHRASES = 10
MAX_SEGMENT_CHARS = 400
MAX_EXPLANATION = 300
MAX_LABEL_CHARS = 120
DEFAULT_MEMBER_ACTION = "includes"
# `X is a <role> of Y` is drafted as Y has <Role>, <Role> includes X.
ROLE_NOUNS = frozenset(
    {
        "client",
        "customer",
        "partner",
        "supplier",
        "vendor",
        "subsidiary",
        "division",
        "member",
        "affiliate",
        "distributor",
        "reseller",
        "contractor",
        "agent",
        "branch",
        "unit",
    }
)
ROLE_ACTION = "has"
ROLE_MEMBER_ACTION = "includes"
_ROLE_PATTERN = re.compile(r"^(?:is|are) (?:a|an|the|one of the) ([a-z]+?) of$")
REFUSED_ACTIONS = frozenset({"is a", "equivalent to"})

_WORDS = re.compile(r"[a-z0-9][a-z0-9&'-]*")
# UAX 29 joiners: MidLetter joins two letters, MidNum two digits, MidNumLet either (the
# apostrophe counts as MidNumLet). The hyphen joins any two word characters, a stricter rule.
_MID_LETTER = frozenset("\u003a\u00b7\u0387\u055f\u05f4\u2027\ufe13\ufe55\uff1a")
_MID_NUM = frozenset(
    "\u002c\u003b\u037e\u0589\u060c\u060d\u066c\u07f8\u2044\ufe10\ufe14\ufe50\ufe54\uff0c\uff1b"
)
_MID_NUM_LET = frozenset("\u0027\u002e\u2018\u2019\u2024\ufe52\uff07\uff0e")
_HYPHEN = "-"
# Punctuation that may join the words of one name inside a grounded label.
_LABEL_JOINERS = frozenset("&./-'’+")
# A full stop followed by whitespace, or any other sentence-ending mark, ends a sentence.
_SENTENCE_END = re.compile(r"\.\s|[!?;:]")


@dataclass
class ModelStep:
    outcome: LlmOutcome
    planned: list[PlannedIntent] = field(default_factory=list)
    unresolved: list[UnresolvedPhrase] = field(default_factory=list)
    # The sentences the model found, as code-point ranges of the request's text, in order.
    segments: list[tuple[int, int]] = field(default_factory=list)


class _InvalidAnswer(Exception):
    """The answer failed the schema or a check the schema cannot express."""


@dataclass(frozen=True)
class Reading:
    """How the model reads the input: one typed sentence, a whole speech transcript, or one
    document sentence with its neighbours as context."""

    mode: Literal["sentence", "speech", "document"] = "sentence"
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()

    @property
    def speech(self) -> bool:
        return self.mode == "speech"

    @property
    def model_first(self) -> bool:
        """Speech and document sentences go to the model first; typed text to the grammar."""
        return self.mode != "sentence"


def enabled(view: OntologyView) -> bool:
    """True when the step can be tried: a provider is configured and the tenant's monthly token
    cap is above 0. Budgets and the provider's answer are checked when the step runs."""
    if get_llm_client() is None:
        return False
    settings = view.settings
    return (settings.llm_monthly_token_cap if settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP) > 0


async def run(
    caller: Caller,
    drafter: Drafter,
    sentence: str,
    text: str,
    turns: list[StoredTurn],
    reading: Reading | None = None,
) -> ModelStep:
    """The model step for `sentence` (`text` is the sentence after its domain prefix)."""
    try:
        return await _run(caller, drafter, sentence, text, turns, reading or Reading())
    except Exception:
        logger.exception("the teach extraction step failed; the grammar's result stands")
        return ModelStep("provider_error")


async def _run(
    caller: Caller,
    drafter: Drafter,
    sentence: str,
    text: str,
    turns: list[StoredTurn],
    reading: Reading,
) -> ModelStep:
    client = get_llm_client()
    if client is None:
        return ModelStep("not_configured")
    settings = drafter.view.settings
    cap = settings.llm_monthly_token_cap if settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
    if cap <= 0:
        return ModelStep("budget_exhausted")
    actor_kind = caller.actor_kind.value
    if not await try_charge(Budget.LLM, caller.tenant_id, actor_kind, caller.user_id):
        return ModelStep("rate_limited")
    handles = _candidates(caller, drafter, text, turns)
    config = get_settings()
    request = LlmRequest(
        system=SYSTEM_PROMPT,
        user=_context(drafter, text, turns, handles, reading),
        output_schema=OUTPUT_SCHEMA,
        # The answer bound plus the reasoning allowance: a provider's output bound counts
        # reasoning tokens too. The answer's own size is bounded by its validation.
        max_output_tokens=(SPEECH_MAX_OUTPUT_TOKENS if reading.speech else MAX_OUTPUT_TOKENS)
        + config.llm_reasoning_allowance_tokens,
        timeout_seconds=(
            config.llm_speech_timeout_seconds if reading.speech else config.llm_timeout_seconds
        ),
    )
    upper_bound = client.estimate_input_tokens(request) + request.max_output_tokens
    reservation = await llm_usage_service.reserve(caller.tenant_id, upper_bound, cap)
    if reservation is None:
        return ModelStep("budget_exhausted")

    def record(outcome: str, tokens_in: int, tokens_out: int, cost: float, ms: int) -> CallRecord:
        return CallRecord(
            tenant_id=caller.tenant_id,
            actor_kind=actor_kind,
            actor_id=caller.user_id,
            company_id=drafter.company_id,
            purpose=llm_usage_service.TEACH_EXTRACTION,
            provider=client.provider,
            model=client.model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_eur=cost,
            latency_ms=ms,
            outcome=outcome,
        )

    # Whatever happens from here on, the reservation is settled and one cost row is written:
    # an unexpected error while reading the answer settles as invalid output.
    outcome, usage = "invalid_output", (0, 0, 0.0, 0)
    try:
        try:
            answer = await client.complete(request)
        except LlmCallError as exc:
            outcome = "timeout" if isinstance(exc, LlmTimeout) else "provider_error"
            usage = (exc.input_tokens, exc.output_tokens, exc.cost_eur, exc.latency_ms)
            return ModelStep(outcome)
        except Exception:
            logger.exception("the language model adapter failed unexpectedly")
            outcome = "provider_error"
            return ModelStep(outcome)
        usage = (answer.input_tokens, answer.output_tokens, answer.cost_eur, answer.latency_ms)
        try:
            step = _interpret(answer.text, handles, drafter, sentence, text, reading)
        except _InvalidAnswer as exc:
            logger.info("the teach extraction answer was refused: %s", exc)
            return ModelStep("invalid_output")
        except Exception:
            logger.exception("reading the teach extraction answer failed unexpectedly")
            return ModelStep("invalid_output")
        outcome = "used"
        return step
    finally:
        await _settle(reservation, record(outcome, *usage))


async def _settle(reservation: llm_usage_service.Reservation, record: CallRecord) -> None:
    try:
        await llm_usage_service.settle(reservation, record)
    except Exception:
        logger.exception("settling a language model call failed; its reservation stays counted")


def _candidates(
    caller: Caller, drafter: Drafter, text: str, turns: list[StoredTurn]
) -> list[Concept]:
    """Up to 200 concepts for the model, the company root first, then by relevance."""
    view = drafter.view
    company_id = drafter.company_id
    cross = bool(view.settings and view.settings.cross_company)
    phrases = _phrases(text)

    def allowed(c: Concept | None) -> bool:
        if c is None or c.dying_at is not None or c.id not in view.concepts:
            return False
        if c.company_id == company_id:
            return True
        return cross and c.company_id in view.companies and can_read(caller.grants, c.company_id)

    chosen: list[Concept] = []
    seen: set[uuid.UUID] = set()
    others = 0

    def take(c: Concept | None) -> None:
        nonlocal others
        if c is None or len(chosen) >= MAX_CANDIDATES or c.id in seen or not allowed(c):
            return
        foreign = c.company_id != company_id
        if foreign and others >= MAX_OTHER_COMPANY_CANDIDATES:
            return
        others += foreign
        seen.add(c.id)
        chosen.append(c)

    take(drafter.root)
    referenced: list[Concept | None] = []
    for turn in reversed(turns):
        referenced.extend(view.concepts.get(concept_id) for concept_id in turn.concept_ids)
        referenced.extend(drafter.resolve(label) for label in turn.new_labels)
    matched = [c for c in drafter.mine if _matches(c.label, phrases)]
    # Concepts the sentence names keep their places: session references never crowd them out,
    # so the model can cite them by handle instead of proposing their labels again.
    unseen = [c.id for c in matched if c.id not in seen]
    named = set(unseen[: MAX_CANDIDATES - len(chosen)])
    for c in referenced:
        owed = len(named - seen)
        if c is not None and c.id not in named and len(chosen) + owed >= MAX_CANDIDATES:
            continue
        take(c)
    for c in matched:
        take(c)
    for c in [*referenced, *matched]:
        if c is None or c.company_id != company_id:
            continue
        take(view.concepts.get(c.parent_id) if c.parent_id else None)
        for child in view.children_of(c.id):
            take(child)
    if cross:
        foreign = [
            c
            for c in view.live_concepts()
            if c.company_id != company_id and _matches(c.label, phrases)
        ]
        for c in sorted(foreign, key=lambda c: (c.born_at, str(c.id))):
            take(c)
    if drafter.dom_key:
        for c in drafter.mine:
            if view.domain_key(c) == drafter.dom_key:
                take(c)
    for c in sorted(drafter.mine, key=lambda c: (c.born_at, str(c.id)), reverse=True):
        take(c)
    return chosen


def _context(
    drafter: Drafter,
    text: str,
    turns: list[StoredTurn],
    handles: list[Concept],
    reading: Reading,
) -> str:
    """The user message: the call's data as JSON, with handles in place of every id."""
    view = drafter.view
    handle_of = {c.id: f"c{i}" for i, c in enumerate(handles)}

    def ref(concept: Concept | None, label: str) -> str:
        return handle_of.get(concept.id, label) if concept else label

    candidates: list[dict[str, Any]] = []
    for c in handles:
        entry: dict[str, Any] = {
            "handle": handle_of[c.id],
            "label": c.label,
            "domain": view.domain_key(c),
            "parent": handle_of.get(c.parent_id) if c.parent_id else None,
            "pending": bool(c.pending),
        }
        if c.company_id != drafter.company_id:
            entry["company"] = view.companies[c.company_id].name
        candidates.append(entry)
    data: dict[str, Any] = {
        "mode": reading.mode,
        "sentence": text,
        "sentenceLength": len(text),
        "domainPrefix": drafter.dom_key,
        "company": view.companies[drafter.company_id].name,
        "sessionTurns": [
            {
                "sentence": t.sentence,
                "referenced": [handle_of[i] for i in t.concept_ids if i in handle_of],
                "introduced": [ref(drafter.resolve(label), label) for label in t.new_labels],
            }
            for t in turns
        ],
        "candidates": candidates,
        "domainTemplates": [
            {"key": key, "name": t.name}
            for key, t in sorted(view.templates.items(), key=lambda kv: kv[1].position)
        ],
    }
    if reading.mode == "document":
        data["neighbours"] = {"before": list(reading.before), "after": list(reading.after)}
    return json.dumps(data, ensure_ascii=False)


def _interpret(
    raw: str,
    handles: list[Concept],
    drafter: Drafter,
    sentence: str,
    text: str,
    reading: Reading,
) -> ModelStep:
    """Validates the whole answer, then maps each confident intent to drafts."""
    try:
        answer = TeachExtractionAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise _InvalidAnswer(f"{exc.error_count()} schema errors") from None
    if not reading.speech and (
        len(answer.intents) > MAX_SENTENCE_INTENTS or len(answer.unresolved) > MAX_SENTENCE_PHRASES
    ):
        raise _InvalidAnswer("too many intents or phrases for one sentence")
    segments, sources = _ranges(answer, text)
    sent = {c.id for c in handles}
    cross_company = bool(drafter.view.settings and drafter.view.settings.cross_company)
    checked: list[_Checked] = []
    earlier = _grounded_labels(answer, sources, text)
    for intent, source in zip(answer.intents, sources, strict=True):
        if reading.speech and intent.segment is None:
            raise _InvalidAnswer("a transcript intent names no segment")
        index = intent.segment if intent.segment is not None else 0
        if index >= len(segments):
            raise _InvalidAnswer("an intent names a segment that was not given")
        if reading.speech and intent.explanation and len(intent.explanation) > 120:
            raise _InvalidAnswer("a transcript explanation is longer than 120 characters")
        seg_start, seg_end = segments[index]
        if not seg_start <= source[0] < source[1] <= seg_end:
            raise _InvalidAnswer("an intent's source lies outside its segment")
        # Each new label is reused as a candidate sent in this call, or grounded in the
        # caller's words inside the source range; the self-join checks run after that. An
        # ungrounded subject or object sinks the intent; an ungrounded member is left out alone.
        raw = [intent.subject, intent.object, *(intent.members or [])]
        placed = [_end(ref, handles, sent, drafter, text, source, earlier) for ref in raw]
        grounded = placed[0] is not None and placed[1] is not None
        dropped = sum(1 for end in placed[2:] if end is None)
        ends = [end for end in placed if end is not None]
        if any(_same(a, b) for i, a in enumerate(ends) for b in ends[i + 1 :]):
            raise _InvalidAnswer("an intent joins a concept to itself or repeats a member")
        foreign = [
            e for e in ends if e.concept is not None and e.concept.company_id != drafter.company_id
        ]
        if foreign:
            both_sent = all(
                end is not None and end.concept is not None and end.concept.id in sent
                for end in placed[:2]
            )
            if intent.kind != "rel" or intent.members or not both_sent or not cross_company:
                raise _InvalidAnswer(
                    "only a relation between two sent candidates crosses companies"
                )
        action = member_action = None
        if intent.kind == "rel":
            assert intent.action is not None
            action = _action(intent.action)
            if intent.members:
                member_action = _action(intent.member_action or DEFAULT_MEMBER_ACTION)
        subject, obj = placed[0], placed[1]
        members = [end for end in placed[2:] if end is not None] if grounded else []
        # A grouping stays inside the taught company, so a role is read only between its own
        # concepts or new labels.
        own = grounded and not foreign
        role = _role_end(action, obj, drafter, text, source) if own else None
        if role is not None and subject is not None and not members:
            # `X is a <role> of Y`: Y has the role, and the role includes X.
            subject, obj, members = obj, role, [subject]
            action, member_action = ROLE_ACTION, ROLE_MEMBER_ACTION
            # `Partner is a partner of Acme` would make the role include itself.
            flipped = [subject, obj, *members]
            if any(_same(a, b) for i, a in enumerate(flipped) for b in flipped[i + 1 :]):
                raise _InvalidAnswer("an intent joins a concept to itself or repeats a member")
        checked.append(
            _Checked(
                intent,
                subject,
                obj,
                members,
                action,
                member_action,
                index,
                source,
                grounded,
                dropped,
            )
        )

    offset = len(sentence) - len(text)
    # A sentence the model did not split is one segment covering it, domain prefix included.
    step = ModelStep(
        "used",
        segments=[(start + offset, end + offset) for start, end in segments]
        if answer.segments
        else [(0, len(sentence))],
    )
    lists: dict[int, list[PlannedIntent]] = {}
    list_sizes: dict[int, int] = {}
    stated: dict[int, int] = {}
    for c in checked:
        intent = c.intent
        if intent.list_id is not None:
            list_sizes[intent.list_id] = list_sizes.get(intent.list_id, 0) + 1
            if intent.stated_count is not None:
                stated.setdefault(intent.list_id, intent.stated_count)
        span = (c.source[0] + offset, c.source[1] + offset)
        where = sentence[span[0] : span[1]][:400]
        if not c.grounded or c.subject is None or c.obj is None:
            step.unresolved.append(UnresolvedPhrase(text=where, reason="ungrounded_label"))
            continue
        if intent.confidence < MIN_CONFIDENCE:
            step.unresolved.append(UnresolvedPhrase(text=where, reason="low_confidence"))
            continue
        if c.dropped:
            step.unresolved.append(UnresolvedPhrase(text=where, reason="ungrounded_label"))
            if not c.members:
                # A group whose every member is ungrounded is not drafted empty.
                continue
        note = DraftNote(
            extractor="llm",
            confidence=intent.confidence,
            explanation=intent.explanation,
            segment=c.segment,
            source_span=SourceSpan(start=span[0], end=span[1]),
        )
        if intent.kind == "rel":
            assert c.action is not None
            planned = drafter.model_rel(c.subject, c.obj, c.action, note, intent.domain_key)
            for member in c.members:
                assert c.member_action is not None and member is not None
                group = End(c.obj.concept, c.obj.label, c.obj.text)
                joined = drafter.model_rel(group, member, c.member_action, note, intent.domain_key)
                planned.drafts.extend(joined.drafts)
                planned.statements.extend(joined.statements)
                planned.concept_ids.extend(
                    i for i in joined.concept_ids if i not in planned.concept_ids
                )
            if c.members and intent.stated_count is not None:
                _note_count(planned, intent.stated_count, len(c.members))
        else:
            planned = drafter.model_spec(c.subject, c.obj, intent.rule, note, intent.domain_key)
        planned.span = intent.span
        planned.segment = c.segment
        step.planned.append(planned)
        if intent.list_id is not None:
            lists.setdefault(intent.list_id, []).append(planned)
    for list_id, planned_list in lists.items():
        if list_id in stated and stated[list_id] != list_sizes[list_id]:
            for planned in planned_list:
                _note_count(planned, stated[list_id], list_sizes[list_id])
    for phrase in answer.unresolved:
        where = None
        if phrase.source is not None and phrase.source.start < len(text):
            start, end = phrase.source.start, min(phrase.source.end, len(text))
            where = sentence[start + offset : end + offset]
        step.unresolved.append(
            UnresolvedPhrase(
                text=(where or phrase_in(sentence, phrase.text))[:400], reason=phrase.reason
            )
        )
    return step


@dataclass(frozen=True)
class _Checked:
    intent: AnswerIntent
    subject: End | None
    obj: End | None
    members: list[End | None]
    action: str | None
    member_action: str | None
    segment: int
    source: tuple[int, int]
    grounded: bool
    # Members of a grouping intent left out as ungrounded.
    dropped: int = 0


def _ranges(
    answer: TeachExtractionAnswer, text: str
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """The answer's segments in order (one covering the text when it gives none), and each
    intent's source range.

    The model's segment offsets are approximate: each segment is trimmed of surrounding
    whitespace and a boundary that cuts a word is moved out to the word's edge. Each intent's
    source is then located from its quote, and a segment is widened to cover the sources of its
    intents; a source is never chosen where that widening would reach into another segment. The
    order, overlap and length checks run on the result."""
    words = _words(text)
    if not answer.segments:
        whole = [(0, len(text))]
        return whole, [_locate(intent, text, words, whole, 0) for intent in answer.intents]
    snapped: list[tuple[int, int]] = []
    for i, seg in enumerate(answer.segments):
        if seg.index != i:
            raise _InvalidAnswer("a segment is out of order")
        snapped.append(_snap(text, words, *_clamp(seg.start, seg.end, text)))
    owners = [intent.segment if intent.segment is not None else 0 for intent in answer.intents]
    sources = [
        _locate(intent, text, words, snapped, own)
        for intent, own in zip(answer.intents, owners, strict=True)
    ]
    out: list[tuple[int, int]] = []
    last_end = 0
    for i, (start, end) in enumerate(snapped):
        for own, (a, b) in zip(owners, sources, strict=True):
            if own == i:
                start, end = min(start, a), max(end, b)
        if start >= end or start < last_end or end - start > MAX_SEGMENT_CHARS:
            raise _InvalidAnswer("segments overlap, go backwards or are too long")
        out.append((start, end))
        last_end = end
    return out, sources


def _clamp(start: int, end: int, text: str) -> tuple[int, int]:
    """A model range with its end clamped to the text's length: the model overshoots range ends
    by a character or two. A range left empty by the clamp makes the answer invalid."""
    end = min(end, len(text))
    if start >= end:
        raise _InvalidAnswer("a range lies outside the text")
    return start, end


def _snap(text: str, words: list[tuple[int, int]], start: int, end: int) -> tuple[int, int]:
    """`[start, end)` without surrounding whitespace, with a boundary inside a word moved out
    to that word's edge."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    for a, b in words:
        if a < start < b:
            start = a
        if a < end < b:
            end = b
    return start, end


def _locate(
    intent: AnswerIntent,
    text: str,
    words: list[tuple[int, int]],
    segments: list[tuple[int, int]],
    own: int,
) -> tuple[int, int]:
    """The intent's source range, found from its quoted words rather than the model's offsets.

    A model counts characters unreliably (it drops a space, or counts UTF-16 units or bytes), so
    when the intent quotes its words in `span` the range is an occurrence of that quote in
    `text`, exact or after whitespace collapse and case folding. An occurrence whose widening of
    the intent's segment would reach into another segment is never chosen. Of the rest, in
    order: a whole-word occurrence inside the intent's own segment; any other whole-word
    occurrence; an occurrence cutting a word. Ties go to an exact match, then to the occurrence
    nearest the model's own start. The range is always a slice of the caller's input, so
    grounding still judges it word by word. Without a quote, or when no occurrence qualifies,
    the model's offsets stand."""
    claimed = _clamp(intent.source.start, intent.source.end, text)
    quote = (intent.span or "").strip()
    if not quote:
        return claimed
    found: dict[tuple[int, int], int] = dict.fromkeys(_occurrences_exact(text, quote), 0)
    for r in _occurrences_folded(text, quote):
        found.setdefault(r, 1)
    home = segments[own] if own < len(segments) else None
    others = [seg for j, seg in enumerate(segments) if j != own]

    def reaches_another(r: tuple[int, int]) -> bool:
        lo, hi = (min(home[0], r[0]), max(home[1], r[1])) if home else r
        return any(lo < b and hi > a for a, b in others)

    def rank(r: tuple[int, int]) -> tuple[int, int, int, int]:
        whole = not any(a < r[0] < b or a < r[1] < b for a, b in words)
        inside = home is not None and home[0] <= r[0] and r[1] <= home[1]
        tier = 0 if whole and inside else 1 if whole else 2
        return (tier, found[r], abs(r[0] - claimed[0]), r[0])

    choices = [r for r in found if not reaches_another(r)]
    return min(choices, key=rank) if choices else claimed


def _occurrences_exact(text: str, quote: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    at = text.find(quote)
    while at >= 0:
        out.append((at, at + len(quote)))
        at = text.find(quote, at + 1)
    return out


def _occurrences_folded(text: str, quote: str) -> list[tuple[int, int]]:
    """Occurrences of `quote` in `text` with whitespace runs collapsed and case folded on both
    sides, as ranges of the original `text`."""
    folded: list[str] = []
    origin: list[int] = []
    for i, c in enumerate(text):
        if c.isspace():
            if folded and folded[-1] == " ":
                continue
            folded.append(" ")
            origin.append(i)
            continue
        for f in c.casefold():
            folded.append(f)
            origin.append(i)
    haystack = "".join(folded)
    needle = " ".join(quote.split()).casefold()
    out: list[tuple[int, int]] = []
    at = haystack.find(needle) if needle else -1
    while at >= 0:
        out.append((origin[at], origin[at + len(needle) - 1] + 1))
        at = haystack.find(needle, at + 1)
    return out


def _ground(label: str, text: str, source: tuple[int, int]) -> str | None:
    """The caller's own words in `text[source]` that `label` names, as a label, or None.

    Words are found over the whole input, so a source range that cuts into a word grounds
    nothing; only words lying wholly inside the range count. Each word is normalised on its own
    (NFKC, case folded, singular), so the matched run maps back to the original words. Between
    two words the label must carry the same characters as the input: whitespace (any run
    compares as one space) or the joining punctuation of names (`L&S`, `R&D`, `A/B`, `O'Neil`);
    a sentence end, a comma or any other character never joins words into one label.
    Characters around the words are dropped, except an abbreviation's closing full stop
    (`S.A.`), which the input must carry too. The label is sliced from the original input and
    put through the casing rule and the label rules, never taken from the model's string."""
    start, end = source
    words = _words(text)
    if any(a < start < b or a < end < b for a, b in words):
        return None
    inside = [(a, b) for a, b in words if a >= start and b <= end]
    label = unicodedata.normalize("NFC", label)
    label_words = _words(label)
    wanted = [_fold(label[a:b]) for a, b in label_words]
    n = len(wanted)
    if not n:
        return None
    gaps = [label[x[1] : y[0]] for x, y in zip(label_words, label_words[1:], strict=False)]
    # Characters around the label's words are not part of it, except an abbreviation's closing
    # full stop (`S.A.`).
    abbreviation = "." in label[label_words[-1][0] : label_words[-1][1]]
    tail = "." if abbreviation and label[label_words[-1][1] :].startswith(".") else ""
    if any(not _joins_label(g) for g in gaps):
        return None
    for i in range(len(inside) - n + 1):
        run = inside[i : i + n]
        if [_fold(text[a:b]) for a, b in run] != wanted:
            continue
        spoken = [text[x[1] : y[0]] for x, y in zip(run, run[1:], strict=False)]
        if any(_gap(a) != _gap(b) for a, b in zip(spoken, gaps, strict=True)):
            continue
        first, last = run[0][0], run[-1][1] + len(tail)
        if last > end or text[run[-1][1] : last] != tail:
            continue
        if _part_of_name(text, first, last):
            continue
        candidate = title(unicodedata.normalize("NFKC", text[first:last]))
        if _valid_label(candidate):
            return candidate
    return None


def _part_of_name(text: str, first: int, last: int) -> bool:
    """True when joining punctuation ties `text[first:last]` to a word next to it, as `L` is
    tied to `S` in `L&S`: the run is then only part of a name."""
    before = first >= 2 and text[first - 1] in _LABEL_JOINERS and _word_char(text[first - 2])
    after = last + 1 < len(text) and text[last] in _LABEL_JOINERS and _word_char(text[last + 1])
    return before or after


def _joins_label(gap: str) -> bool:
    """True when `gap` may sit between two words of a label: whitespace and joining
    punctuation, never a sentence end."""
    if any(c not in _LABEL_JOINERS and not c.isspace() for c in gap):
        return False
    return not _SENTENCE_END.search(gap)


def _gap(gap: str) -> str:
    """A gap between two words as compared: NFKC, every whitespace run as one space."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", gap))


def _words(text: str) -> list[tuple[int, int]]:
    """Code-point ranges of the words of `text`, by the UAX 29 word rules that matter here.

    Letters, digits and connector punctuation make words. Combining marks (Mn, Mc, Me) and
    format characters (Cf: ZWNJ, ZWJ, soft hyphen, word joiner) after a word character stay in
    the word (rule WB4), so an accent in decomposed text, a Thai or Devanagari vowel sign or a
    Persian ZWNJ never ends it. A MidLetter joiner between two letters, a MidNum joiner between
    two digits, a MidNumLet joiner between two letters or two digits, and a hyphen between any
    two word characters keep the word whole (`node.js`, `node．js`, `insight’s`, `3,000`).
    Ranges index the text as given, so decomposed and precomposed input give the same words."""
    words: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        if not _word_char(text[i]):
            i += 1
            continue
        start = i
        last = text[i]
        i += 1
        while i < n:
            c = text[i]
            if _word_char(c):
                last = c
                i += 1
            elif _extends(c):
                i += 1
            elif _joins(c, last, _next_base(text, i + 1)):
                i += 1
            else:
                break
        words.append((start, i))
    return words


def _word_char(c: str) -> bool:
    return c.isalnum() or unicodedata.category(c) in ("Nl", "No", "Pc")


def _extends(c: str) -> bool:
    """Combining marks and format characters, which extend the word before them (WB4)."""
    return unicodedata.category(c) in ("Mn", "Mc", "Me", "Cf")


def _next_base(text: str, i: int) -> str | None:
    """The next word character from `i`, skipping marks and format characters, or None."""
    while i < len(text) and _extends(text[i]):
        i += 1
    return text[i] if i < len(text) and _word_char(text[i]) else None


def _joins(c: str, before: str, after: str | None) -> bool:
    if after is None:
        return False
    letters = before.isalpha() and after.isalpha()
    digits = before.isdigit() and after.isdigit()
    if c == _HYPHEN:
        return True
    if c in _MID_LETTER:
        return letters
    if c in _MID_NUM:
        return digits
    if c in _MID_NUM_LET:
        return letters or digits
    return False


def _valid_label(label: str) -> bool:
    """The label rules every model label meets: 1 to 120 characters, no surrounding space, no
    markup, control, line separator or format character."""
    return (
        0 < len(label) <= MAX_LABEL_CHARS
        and label == label.strip()
        and not has_refused_character(label)
    )


def _fold(word: str) -> str:
    return singular(unicodedata.normalize("NFKC", word).casefold())


def _action(raw: str) -> str:
    action = normalise_action(raw)
    if not action or action in REFUSED_ACTIONS:
        raise _InvalidAnswer("a rel action is is a or equivalent to")
    return action


def _note_count(planned: PlannedIntent, stated: int, listed: int) -> None:
    """Drafts follow the list; the reviewer learns that the stated number differed."""
    remark = f"stated {stated}, listed {listed}"
    current = planned.note.explanation
    text = f"{current} {remark}" if current else remark
    if len(text) > MAX_EXPLANATION:
        text = f"{current[: MAX_EXPLANATION - len(remark) - 1]} {remark}" if current else remark
    planned.note = planned.note.model_copy(update={"explanation": text})


def _end(
    ref: Any,
    handles: list[Concept],
    sent: set[uuid.UUID],
    drafter: Drafter,
    text: str,
    source: tuple[int, int],
    earlier: list[str] | None = None,
) -> End | None:
    """An intent end: a cited candidate; a new label naming a candidate sent in this call,
    reused as is; or a new label grounded in the caller's words - inside this intent's range,
    or as a label another intent of the same answer grounded in its own range (`earlier`) - and
    then resolved to an existing concept of the company when one has that label. None when a
    new label is ungrounded."""
    if isinstance(ref, CandidateRef):
        index = int(ref.candidate[1:])
        if index >= len(handles):
            raise _InvalidAnswer("a cited candidate was not sent")
        concept = handles[index]
        return End(concept, concept.label, concept.label)
    label = title(unicodedata.normalize("NFKC", ref.new_label))
    reused = drafter.resolve(label)
    if reused is not None and reused.id in sent:
        return End(reused, reused.label, reused.label)
    spoken = _ground(label, text, source) or _repeated(label, earlier or [])
    if spoken is None:
        return None
    return End(drafter.resolve(spoken), spoken, spoken, cited_new=True)


def _grounded_labels(
    answer: TeachExtractionAnswer, sources: list[tuple[int, int]], text: str
) -> list[str]:
    """The new labels of the answer that are grounded inside their own intent's range, each as
    the caller's words sliced from the input."""
    labels: list[str] = []
    for intent, source in zip(answer.intents, sources, strict=True):
        for ref in [intent.subject, intent.object, *(intent.members or [])]:
            if isinstance(ref, CandidateRef):
                continue
            spoken = _ground(title(unicodedata.normalize("NFKC", ref.new_label)), text, source)
            if spoken is not None and spoken not in labels:
                labels.append(spoken)
    return labels


def _repeated(label: str, earlier: list[str]) -> str | None:
    """The label another intent of the answer already grounded that `label` repeats, word for
    word as the grounding compares words, or None. The result is that intent's slice of the
    caller's input, so only the caller's own words can name a new concept."""
    for spoken in earlier:
        if (_ground(label, spoken, (0, len(spoken))) or "").casefold() == spoken.casefold():
            return spoken
    return None


def _role_end(
    action: str | None,
    holder: End | None,
    drafter: Drafter,
    text: str,
    source: tuple[int, int],
) -> End | None:
    """The role concept of a `rel` intent whose action reads `is a <role> of`: the holder's
    existing child of that label, else the company's concept of that label, else the role noun
    as a new label grounded in the caller's words. None for any other action, or when the noun
    is not in the caller's words."""
    found = _ROLE_PATTERN.match(action or "")
    if found is None or holder is None:
        return None
    noun = found.group(1)
    if singular(noun) not in ROLE_NOUNS:
        return None
    wanted = {noun, singular(noun)}
    if holder.concept is not None:
        for child in drafter.view.children_of(holder.concept.id):
            if {child.label.lower(), singular(child.label.lower())} & wanted:
                return End(child, child.label, child.label)
    spoken = _ground(title(noun), text, source)
    if spoken is None:
        return None
    return End(drafter.resolve(spoken), spoken, spoken, cited_new=True)


def _same(a: End, b: End) -> bool:
    if a.concept is not None or b.concept is not None:
        return a.concept is not None and b.concept is not None and a.concept.id == b.concept.id
    return a.label.lower() == b.label.lower()


def _phrases(text: str) -> set[str]:
    words = _WORDS.findall(text.lower())
    out: set[str] = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i : i + n])
            out.add(gram)
            out.add(" ".join([*words[i : i + n - 1], singular(words[i + n - 1])]))
    return out


def _matches(label: str, phrases: set[str]) -> bool:
    lower = label.lower()
    return lower in phrases or singular(lower) in phrases
