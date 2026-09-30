"""The language model step of a teach parse: context, budgets, the call, validation, mapping.

The step runs behind the grammar, only when a fallback trigger holds. In order: a provider must
be configured and the tenant's monthly token cap above 0; the caller's hourly `llm` budget is
charged; the call's upper bound is reserved against the monthly cap and committed; the adapter
calls the model with nothing but the sentence, the session's recent turns, the company name, up
to 200 candidate concepts as per-call handles (`c0` is the company root), the domain templates,
the action guidance and up to three worked examples from the example library, picked by lexical
likeness to the text, then the company's own lessons, negatives, speech aliases and habits
learnt from its people's decisions; the reservation's estimate counts all of it. The reservation is
settled and a cost record stored whatever happens. A valid answer is mapped to drafts with the
grammar's mapping; anything else leaves the grammar's result standing and the step reports why.
A streamed call reads each part of the answer as it arrives with the same checks, for the
client to show early; only the whole answer decides the step. The step never raises.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import time
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.ai.prompts.teach_extraction import (
    EXAMPLE_LIBRARY,
    MAX_OUTPUT_TOKENS,
    MAX_RETRIEVED_EXAMPLE_TOKENS,
    MAX_RETRIEVED_EXAMPLES,
    OUTPUT_SCHEMA,
    SPEECH_MAX_OUTPUT_TOKENS,
    SPEECH_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    render_example,
)
from app.auth import Caller
from app.clients.llm_client import (
    LlmCallError,
    LlmClient,
    LlmRequest,
    LlmTimeout,
    TextListener,
    estimate_tokens,
    get_llm_client,
)
from app.config import LlmProfile, get_settings
from app.models.api.settings import DEFAULT_LLM_MONTHLY_TOKEN_CAP
from app.models.api.teach import (
    DraftNote,
    LlmOutcome,
    SourceSpan,
    UnresolvedPhrase,
    UnresolvedReason,
)
from app.models.llm.teach_extraction_answer import (
    AnswerIntent,
    CandidateRef,
    TeachExtractionAnswer,
)
from app.models.storage.concept import Concept
from app.repositories.llm_call_repository import CallRecord
from app.repositories.teach_session_turn_repository import StoredTurn
from app.services import learning_service, llm_usage_service
from app.services.ontology_view_service import OntologyView
from app.services.rate_limit_service import Budget, try_charge
from app.services.teach_draft_service import Drafter, End, PlannedIntent, phrase_in
from app.utilities.action_text import has_refused_character, normalise_action
from app.utilities.example_selection import most_similar, within_budget
from app.utilities.learning_structure import fold
from app.utilities.permissions import can_read
from app.utilities.sound_alike import company_possessive_rest, sounds_like_name
from app.utilities.streamed_json import closed_items
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
MAX_ATTRIBUTE_NAME = 80
MAX_ATTRIBUTE_VALUE = 200
# The inflections an attribute name may differ by from the caller's word; the shortest word an
# inflection is added to, and the shortest stem two inflected words may share.
_INFLECTIONS = ("ing", "es", "ed", "s", "d")
_MIN_STEM = 3
_MIN_SHARED_STEM = 4
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
# A word that tells the example ranking the reading mode, so a transcript favours transcripts.
_MODE_WORD = {"sentence": "mode_sentence", "speech": "mode_speech", "document": "mode_document"}


@dataclass
class ModelStep:
    outcome: LlmOutcome
    planned: list[PlannedIntent] = field(default_factory=list)
    unresolved: list[UnresolvedPhrase] = field(default_factory=list)
    # The sentences the model found, as code-point ranges of the request's text, in order.
    segments: list[tuple[int, int]] = field(default_factory=list)


# Receives the step that the part of a streamed answer received so far gives.
PartialListener = Callable[[ModelStep], Awaitable[None]]


class _InvalidAnswer(Exception):
    """The answer failed the schema or a check the schema cannot express."""


class _UnorderedSegments(Exception):
    """The answer's segments overlap, go backwards, are out of order or are too long."""


class _Stages:
    """Milliseconds spent in each named stage of one step, for the debug log."""

    def __init__(self) -> None:
        self._last = time.perf_counter()
        self._spent: list[tuple[str, int]] = []

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        self._spent.append((stage, int((now - self._last) * 1000)))
        self._last = now

    def __str__(self) -> str:
        return " ".join(f"{stage}={ms}ms" for stage, ms in self._spent)


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


def enabled(view: OntologyView, profile: LlmProfile) -> bool:
    """True when the step can be tried on `profile`: its provider is configured and the tenant's
    monthly token cap is above 0. Budgets and the provider's answer are checked when the step
    runs."""
    if get_llm_client(profile) is None:
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
    *,
    profile: LlmProfile,
    on_partial: PartialListener | None = None,
) -> ModelStep:
    """The model step for `sentence` (`text` is the sentence after its domain prefix), on the
    caller's model profile. Budgets and the monthly cap are the same for every profile.

    With `on_partial` the answer is streamed, and each time it closes another intent the answer
    so far is read as a step and handed to `on_partial` (see `_partials`); the step returned is
    the one the whole answer gives, exactly as without it."""
    try:
        return await _run(
            caller, drafter, sentence, text, turns, reading or Reading(), profile, on_partial
        )
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
    profile: LlmProfile,
    on_partial: PartialListener | None,
) -> ModelStep:
    client = get_llm_client(profile)
    if client is None:
        return ModelStep("not_configured")
    settings = drafter.view.settings
    cap = settings.llm_monthly_token_cap if settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
    if cap <= 0:
        return ModelStep("budget_exhausted")
    actor_kind = caller.actor_kind.value
    stages = _Stages()
    if not await try_charge(Budget.LLM, caller.tenant_id, actor_kind, caller.user_id):
        return ModelStep("rate_limited")
    stages.mark("budget")
    handles = _candidates(caller, drafter, text, turns)
    learning = await learning_service.context_for(drafter.view, drafter.company_id, text, "teach")
    aliases = learning.aliases if learning else []
    config = get_settings()
    allowance = config.llm_profile(profile).reasoning_allowance_tokens
    request = LlmRequest(
        system=SYSTEM_PROMPT,
        user=_context(
            drafter, text, turns, handles, reading, learning.as_data() if learning else {}
        ),
        output_schema=SPEECH_OUTPUT_SCHEMA if reading.speech else OUTPUT_SCHEMA,
        # The answer bound plus the reasoning allowance: a provider's output bound counts
        # reasoning tokens too. The answer's own size is bounded by its validation.
        max_output_tokens=(SPEECH_MAX_OUTPUT_TOKENS if reading.speech else MAX_OUTPUT_TOKENS)
        + allowance,
        timeout_seconds=(
            config.llm_speech_timeout_seconds if reading.speech else config.llm_timeout_seconds
        ),
    )
    stages.mark("context")
    upper_bound = client.estimate_input_tokens(request) + request.max_output_tokens
    reservation = await llm_usage_service.reserve(caller.tenant_id, upper_bound, cap)
    if reservation is None:
        return ModelStep("budget_exhausted")
    stages.mark("reserve")

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
            if on_partial is None:
                answer = await client.complete(request)
            else:
                partials = _partials(
                    client, request, handles, drafter, sentence, text, reading, on_partial
                )
                answer = await client.stream(request, partials)
        except LlmCallError as exc:
            outcome = "timeout" if isinstance(exc, LlmTimeout) else "provider_error"
            usage = (exc.input_tokens, exc.output_tokens, exc.cost_eur, exc.latency_ms)
            return ModelStep(outcome)
        except Exception:
            logger.exception("the language model adapter failed unexpectedly")
            outcome = "provider_error"
            return ModelStep(outcome)
        usage = (answer.input_tokens, answer.output_tokens, answer.cost_eur, answer.latency_ms)
        stages.mark("model")
        try:
            step = _interpret(answer.text, handles, drafter, sentence, text, reading, aliases)
        except _InvalidAnswer as exc:
            logger.info("the teach extraction answer was refused: %s", exc)
            return ModelStep("invalid_output")
        except Exception:
            logger.exception("reading the teach extraction answer failed unexpectedly")
            return ModelStep("invalid_output")
        outcome = "used"
        return step
    finally:
        stages.mark("interpret")
        await _settle(reservation, record(outcome, *usage))
        stages.mark("settle")
        logger.debug(
            "teach extraction on %s (%s, %d input tokens estimated): %s",
            profile,
            outcome,
            upper_bound - request.max_output_tokens,
            stages,
        )


def _partials(
    client: LlmClient,
    request: LlmRequest,
    handles: list[Concept],
    drafter: Drafter,
    sentence: str,
    text: str,
    reading: Reading,
    on_partial: PartialListener,
) -> TextListener:
    """The listener of a streamed answer. Each time the text received so far closes another
    intent (or another segment), the answer so far - its closed intents, segments and phrases -
    goes through `_interpret`, the reading of a whole answer, on a drafter of its own, and the
    step it gives goes to `on_partial`. A part that fails a check gives no step; the whole
    answer decides. A failure here never reaches the call: the listener stops instead."""
    seen = (0, 0)
    received = 0
    stopped = False

    async def listen(raw: str) -> None:
        nonlocal seen, received, stopped
        if stopped:
            return
        if len(raw) < received:
            # A retried attempt starts its answer again.
            seen = (0, 0)
            received = 0
        grown = raw[received:]
        received = len(raw)
        if "}" not in grown:
            return
        items = closed_items(raw)
        intents = items.get("intents", [])
        counts = (len(intents), len(items.get("segments", [])))
        if not intents or counts == seen:
            return
        seen = counts
        part: dict[str, Any] = {"intents": intents, "unresolved": items.get("unresolved", [])}
        if "segments" in items:
            part["segments"] = items["segments"]
        own = Drafter(
            drafter.view, drafter.company_id, drafter.root, drafter.dom_key, drafter.extras
        )
        try:
            answer = client.answer_text(json.dumps(part, ensure_ascii=False), request)
            step = _interpret(answer, handles, own, sentence, text, reading)
        except _InvalidAnswer:
            return
        except Exception:
            logger.exception("reading part of a streamed teach extraction answer failed")
            stopped = True
            return
        try:
            await on_partial(step)
        except Exception:
            logger.exception("handing on part of a streamed teach extraction answer failed")
            stopped = True

    return listen


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
    learning: dict[str, Any] | None = None,
) -> str:
    """The user message: the call's data as JSON, with handles in place of every id. The
    company's learning (`learning`, as data fields) comes last, after the static examples and
    the call's own data."""
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
    # The retrieved examples come first, after the fixed prefix and before the caller's text.
    return json.dumps(
        {"examples": examples_for(text, reading.mode), **data, **(learning or {})},
        ensure_ascii=False,
    )


def examples_for(text: str, mode: str) -> list[dict[str, Any]]:
    """The library examples most like `text` read in `mode`, best first: at most
    MAX_RETRIEVED_EXAMPLES, together within MAX_RETRIEVED_EXAMPLE_TOKENS estimated tokens."""
    shown, texts, costs = _library()
    ranked = most_similar(f"{text} {_MODE_WORD.get(mode, '')}", texts)
    chosen = within_budget(ranked, costs, MAX_RETRIEVED_EXAMPLES, MAX_RETRIEVED_EXAMPLE_TOKENS)
    return [shown[i] for i in chosen]


def example_tokens(example: dict[str, Any]) -> int:
    """The estimated input tokens one shown example adds, by the call's own estimate."""
    return estimate_tokens(LlmRequest("", json.dumps(example, ensure_ascii=False), {}, 0, 0))


@functools.cache
def _library() -> tuple[list[dict[str, Any]], list[str], list[int]]:
    """The library examples as shown to the model, as ranked, and their estimated tokens."""
    shown = [render_example(e) for e in EXAMPLE_LIBRARY]
    return shown, [_example_text(e) for e in EXAMPLE_LIBRARY], [example_tokens(e) for e in shown]


def _example_text(example: dict[str, Any]) -> str:
    """What the ranking compares: the example's text, its candidates' labels and its mode."""
    data = example["input"]
    labels = " ".join(c["label"] for c in data.get("candidates", []))
    return f"{data['sentence']} {labels} {_MODE_WORD[data['mode']]}"


def _interpret(
    raw: str,
    handles: list[Concept],
    drafter: Drafter,
    sentence: str,
    text: str,
    reading: Reading,
    aliases: Sequence[tuple[str, str]] = (),
) -> ModelStep:
    """Validates the whole answer, then maps each confident intent to drafts. `aliases` are the
    company's (heard, meant) speech aliases whose heard form occurs in the text."""
    try:
        answer = TeachExtractionAnswer.model_validate_json(raw)
    except ValidationError as exc:
        raise _InvalidAnswer(f"{exc.error_count()} schema errors") from None
    if not reading.speech and (
        len(answer.intents) > MAX_SENTENCE_INTENTS or len(answer.unresolved) > MAX_SENTENCE_PHRASES
    ):
        raise _InvalidAnswer("too many intents or phrases for one sentence")
    segments, sources, owners = _ranges(answer, text)
    sent = {c.id for c in handles}
    cross_company = bool(drafter.view.settings and drafter.view.settings.cross_company)
    checked: list[_Checked] = []
    earlier = _grounded_labels(answer, sources, text)
    for intent, source, index in zip(answer.intents, sources, owners, strict=True):
        if reading.speech and intent.segment is None:
            raise _InvalidAnswer("a transcript intent names no segment")
        if index >= len(segments):
            raise _InvalidAnswer("an intent names a segment that was not given")
        if reading.speech and intent.explanation and len(intent.explanation) > 120:
            raise _InvalidAnswer("a transcript explanation is longer than 120 characters")
        seg_start, seg_end = segments[index]
        if not seg_start <= source[0] < source[1] <= seg_end:
            raise _InvalidAnswer("an intent's source lies outside its segment")
        if intent.kind == "attr":
            _check_attr_subject(intent.subject, handles, drafter)
            checked.append(_Checked(intent, None, None, [], None, None, index, source, True))
            continue
        assert intent.object is not None
        # Each new label is reused as a candidate sent in this call, or grounded in the
        # caller's words inside the source range; the self-join checks run after that. An
        # ungrounded subject or object sinks the intent; an ungrounded member is left out alone.
        raw = [intent.subject, intent.object, *(intent.members or [])]
        placed = [_end(ref, handles, sent, drafter, text, source, earlier, aliases) for ref in raw]
        # Speech recognition mishears names: a new label that sounds like the name of one of
        # the company's concepts is never drafted beside it; the phrase is listed instead. Each
        # end left out keeps its own reason.
        reasons: list[UnresolvedReason | None] = [
            None if end is not None else "ungrounded_label" for end in placed
        ]
        if reading.speech:
            for i, end in enumerate(placed):
                if end is not None and _misheard(end, drafter):
                    placed[i], reasons[i] = None, "ambiguous_reference"
                elif end is not None:
                    placed[i] = _company_possessive(end, drafter) or end
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
                _distinct(reasons[:2]),
                _distinct(reasons[2:]),
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
    # Attributes this answer drafts: (concept id or new label, name) to value.
    taught: dict[tuple[str, str], str] = {}
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
        if intent.kind == "attr":
            attr = _plan_attr(c, handles, sent, drafter, text, taught, offset)
            if isinstance(attr, PlannedIntent):
                step.planned.append(attr)
            elif attr is not None:
                step.unresolved.append(UnresolvedPhrase(text=where, reason=attr))
            continue
        if not c.grounded or c.subject is None or c.obj is None:
            for reason in c.end_reasons or ("ungrounded_label",):
                step.unresolved.append(UnresolvedPhrase(text=where, reason=reason))
            continue
        if intent.confidence < MIN_CONFIDENCE:
            step.unresolved.append(UnresolvedPhrase(text=where, reason="low_confidence"))
            continue
        if c.dropped:
            for reason in c.member_reasons:
                step.unresolved.append(UnresolvedPhrase(text=where, reason=reason))
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
    # Members of a grouping intent left out as ungrounded or misheard.
    dropped: int = 0
    # Why the subject or object, and why members, were left out: ungrounded_label, or
    # ambiguous_reference for a label that sounds like an existing name; each reason once.
    end_reasons: tuple[UnresolvedReason, ...] = ()
    member_reasons: tuple[UnresolvedReason, ...] = ()


def _ranges(
    answer: TeachExtractionAnswer, text: str
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[int]]:
    """The answer's segments in order (one covering the text when it gives none), each intent's
    source range and each intent's segment index.

    The model's segment offsets are approximate: a boundary that cuts a word is moved to the
    word's nearer edge and each segment is trimmed of surrounding whitespace. Each intent's
    source is then located from its quote, and a segment is widened to cover the sources of its
    intents; a source is never chosen where that widening would reach into another segment.
    Segments that then overlap, go backwards, are out of order or are too long are repaired
    rather than refused (see `_repaired`)."""
    words = _words(text)
    owners = [intent.segment if intent.segment is not None else 0 for intent in answer.intents]
    if not answer.segments:
        whole = [(0, len(text))]
        sources = [_locate(intent, text, words, whole, 0) for intent in answer.intents]
        return whole, sources, owners
    try:
        segments, sources = _ordered(answer, text, words, owners)
    except _UnorderedSegments as exc:
        logger.info("the teach extraction answer's segments were repaired: %s", exc)
        return _repaired(answer, text, words)
    return segments, sources, owners


def _ordered(
    answer: TeachExtractionAnswer, text: str, words: list[tuple[int, int]], owners: list[int]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """The model's own segments, snapped and widened over their intents' sources, and each
    intent's source; raises _UnorderedSegments when they are not in order and apart."""
    snapped: list[tuple[int, int]] = []
    for i, seg in enumerate(answer.segments):
        if seg.index != i:
            raise _UnorderedSegments("a segment is out of order")
        if i and seg.start < answer.segments[i - 1].end:
            raise _UnorderedSegments("segments overlap or go backwards")
        snapped.append(_snap(text, words, *_clamp(seg.start, seg.end, text)))
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
            raise _UnorderedSegments("segments overlap, go backwards or are too long")
        out.append((start, end))
        last_end = end
    return out, sources


def _repaired(
    answer: TeachExtractionAnswer, text: str, words: list[tuple[int, int]]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[int]]:
    """Segments rebuilt from an answer whose own segments are out of order, with each intent's
    source and the index of the segment holding it; the model's segment indices are ignored.

    Each source is located from its quote over the whole text. A text of at most
    MAX_SEGMENT_CHARS is one segment: the Studio sends one spoken sentence per request, which
    has nothing to split. A longer text keeps the model's segments, clamped and snapped to
    words, sorted and merged with each other and with the sources where they overlap; a merged
    segment over MAX_SEGMENT_CHARS is split at word ends that cut no source. The answer is
    refused only when a source cannot be placed in a segment of that length."""
    whole = [(0, len(text))]
    sources = [_locate(intent, text, words, whole, 0) for intent in answer.intents]
    if len(text) <= MAX_SEGMENT_CHARS:
        return whole, sources, [0] * len(sources)
    ranges = list(sources)
    for seg in answer.segments:
        end = min(seg.end, len(text))
        if seg.start < end:
            ranges.append(_snap(text, words, seg.start, end))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(r for r in ranges if r[0] < r[1]):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    segments = [piece for seg in merged for piece in _split(text, words, seg, sources)]
    owners: list[int] = []
    for start, end in sources:
        holding = [i for i, (a, b) in enumerate(segments) if a <= start and end <= b]
        if not holding:
            raise _InvalidAnswer("an intent's source cannot be placed in a segment")
        owners.append(holding[0])
    return segments, sources, owners


def _split(
    text: str,
    words: list[tuple[int, int]],
    segment: tuple[int, int],
    sources: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """`segment` in pieces of at most MAX_SEGMENT_CHARS, each cut at the last word end that
    fits and lies inside no source; raises _InvalidAnswer when no such word end exists."""
    start, end = segment
    pieces: list[tuple[int, int]] = []
    while end - start > MAX_SEGMENT_CHARS:
        cuts = [
            b
            for _, b in words
            if start < b <= start + MAX_SEGMENT_CHARS
            and b < end
            and not any(a < b < z for a, z in sources)
        ]
        if not cuts:
            raise _InvalidAnswer("an intent's source cannot be placed in a segment")
        piece = _trim(text, start, cuts[-1])
        if piece[0] < piece[1]:
            pieces.append(piece)
        start = _trim(text, cuts[-1], end)[0]
    piece = _trim(text, start, end)
    if piece[0] < piece[1]:
        pieces.append(piece)
    return pieces


def _clamp(start: int, end: int, text: str) -> tuple[int, int]:
    """A model range with its end clamped to the text's length: the model overshoots range ends
    by a character or two. A range left empty by the clamp makes the answer invalid."""
    end = min(end, len(text))
    if start >= end:
        raise _InvalidAnswer("a range lies outside the text")
    return start, end


def _snap(text: str, words: list[tuple[int, int]], start: int, end: int) -> tuple[int, int]:
    """`[start, end)` with a boundary inside a word moved to that word's nearer edge, out of the
    range on a tie, and without surrounding whitespace.

    A model's offsets drift by a few code points along a transcript, so a boundary that cuts a
    word mostly lies next to the gap the model meant; moving it to the nearer edge keeps two
    neighbouring segments from both claiming the cut word. When that leaves the range without a
    word, both boundaries move out instead."""
    near_start, near_end = start, end
    out_start, out_end = start, end
    for a, b in words:
        if a < start < b:
            near_start = a if start - a <= b - start else b
            out_start = a
        if a < end < b:
            near_end = b if b - end <= end - a else a
            out_end = b
    start, end = _trim(text, near_start, near_end)
    if start >= end:
        start, end = _trim(text, out_start, out_end)
    return start, end


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
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


def ground_in_sentence(label: str, sentence: str) -> tuple[str, int, int] | None:
    """The words of `sentence` that `label` names, as a label with their code-point range, or
    None: the teach grounding rule applied to one whole document sentence."""
    return _grounded_run(label, sentence, (0, len(sentence)))


def quote_range(text: str, quote: str) -> tuple[int, int] | None:
    """The first occurrence of `quote` in `text`, exact or after whitespace collapse and case
    folding, as a code-point range; None when it does not occur."""
    quote = quote.strip()
    if not quote:
        return None
    found = _occurrences_exact(text, quote) or _occurrences_folded(text, quote)
    return found[0] if found else None


def _ground(label: str, text: str, source: tuple[int, int]) -> str | None:
    """The caller's own words in `text[source]` that `label` names, as a label, or None."""
    grounded = _grounded_run(label, text, source)
    return grounded[0] if grounded else None


def _grounded_run(label: str, text: str, source: tuple[int, int]) -> tuple[str, int, int] | None:
    """The caller's own words in `text[source]` that `label` names, as a label with their range.

    Words are found over the whole input, so a source range that cuts into a word grounds
    nothing; only words lying wholly inside the range count. Each word is normalised on its own
    (NFKC, case folded, singular), so the matched run maps back to the original words. Between
    two words the label must carry the same characters as the input: whitespace (any run
    compares as one space) or the joining punctuation of names (`L&S`, `R&D`, `A/B`, `O'Neil`);
    a sentence end, a comma or any other character never joins words into one label.
    Characters around the words are dropped, except an abbreviation's closing full stop
    (`S.A.`), which the input must carry too. The label is sliced from the original input and
    put through the casing rule and the label rules, never taken from the model's string."""
    for first, last in _runs(label, text, source, _fold):
        candidate = title(unicodedata.normalize("NFKC", text[first:last]))
        if _valid_label(candidate):
            return candidate, first, last
    return None


def _runs(
    phrase: str, text: str, source: tuple[int, int], fold: Callable[[str], str]
) -> Iterator[tuple[int, int]]:
    """Ranges of `text[source]` whose whole words match the words of `phrase` one by one under
    `fold`, with the same separators between them, in order; see `_ground`."""
    start, end = source
    words = _words(text)
    if any(a < start < b or a < end < b for a, b in words):
        return
    inside = [(a, b) for a, b in words if a >= start and b <= end]
    phrase = unicodedata.normalize("NFC", phrase)
    phrase_words = _words(phrase)
    wanted = [fold(phrase[a:b]) for a, b in phrase_words]
    n = len(wanted)
    if not n:
        return
    gaps = [phrase[x[1] : y[0]] for x, y in zip(phrase_words, phrase_words[1:], strict=False)]
    # Characters around the phrase's words are not part of it, except an abbreviation's
    # closing full stop (`S.A.`).
    abbreviation = "." in phrase[phrase_words[-1][0] : phrase_words[-1][1]]
    tail = "." if abbreviation and phrase[phrase_words[-1][1] :].startswith(".") else ""
    if any(not _joins_label(g) for g in gaps):
        return
    for i in range(len(inside) - n + 1):
        run = inside[i : i + n]
        if [fold(text[a:b]) for a, b in run] != wanted:
            continue
        spoken = [text[x[1] : y[0]] for x, y in zip(run, run[1:], strict=False)]
        if any(_gap(a) != _gap(b) for a, b in zip(spoken, gaps, strict=True)):
            continue
        first, last = run[0][0], run[-1][1] + len(tail)
        if last > end or text[run[-1][1] : last] != tail:
            continue
        if _part_of_name(text, first, last):
            continue
        yield first, last


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
    aliases: Sequence[tuple[str, str]] = (),
) -> End | None:
    """An intent end: a cited candidate; a new label naming a candidate sent in this call,
    reused as is; or a new label grounded in the caller's words - inside this intent's range,
    as a label another intent of the same answer grounded in its own range (`earlier`), or as
    the meant label of a company alias whose heard form is in the range - and then resolved to
    an existing concept of the company when one has that label. None when a new label is
    ungrounded."""
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
    spoken = (
        _ground(label, text, source)
        or _repeated(label, earlier or [])
        or alias_grounding(label, text, source, aliases)
    )
    if spoken is None:
        return None
    return End(drafter.resolve(spoken), spoken, spoken, cited_new=True)


def alias_grounding(
    label: str, text: str, source: tuple[int, int], aliases: Sequence[tuple[str, str]]
) -> str | None:
    """The meant label of a company alias that `label` equals, when the alias's heard form is
    grounded in the caller's words inside `text[source]`; None otherwise. The alias came from a
    person's approved correction in the same company, and the caller's own words must still
    carry the heard form, so this is the one case where a label is not the caller's words."""
    wanted = fold(label)
    for heard, meant in aliases:
        if fold(meant) == wanted and _ground(heard, text, source) is not None:
            return meant
    return None


def _misheard(end: End, drafter: Drafter) -> bool:
    """True when `end` is a new label the model gave no candidate for, and it sounds like, but
    is not, the proper name of one of the company's concepts (`Ahmedabus` beside `Amdaris`)."""
    if end.concept is not None:
        return False
    companies = [company.name for company in drafter.view.companies.values()]
    return any(sounds_like_name(end.label, c.label, company_names=companies) for c in drafter.mine)


def _company_possessive(end: End, drafter: Drafter) -> End | None:
    """A new label that starts with the taught company's name misheard ("Inside sales" for
    Insight) as the company's own rest of the label: the existing concept it names (Sales), or
    a new label of those words alone. None when `end` is not such a label."""
    if end.concept is not None:
        return None
    rest = company_possessive_rest(end.label, drafter.view.companies[drafter.company_id].name)
    if rest is None:
        return None
    return End(drafter.resolve(rest), title(rest), rest, cited_new=True)


def _distinct(reasons: list[UnresolvedReason | None]) -> tuple[UnresolvedReason, ...]:
    return tuple(dict.fromkeys(r for r in reasons if r is not None))


def _grounded_labels(
    answer: TeachExtractionAnswer, sources: list[tuple[int, int]], text: str
) -> list[str]:
    """The new labels of the answer that are grounded inside their own intent's range, each as
    the caller's words sliced from the input."""
    labels: list[str] = []
    for intent, source in zip(answer.intents, sources, strict=True):
        if intent.kind == "attr":
            continue
        for ref in [intent.subject, intent.object, *(intent.members or [])]:
            if ref is None or isinstance(ref, CandidateRef):
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


def _check_attr_subject(ref: Any, handles: list[Concept], drafter: Drafter) -> None:
    """An attr intent's cited subject was sent and belongs to the taught company."""
    if not isinstance(ref, CandidateRef):
        return
    index = int(ref.candidate[1:])
    if index >= len(handles):
        raise _InvalidAnswer("a cited candidate was not sent")
    if handles[index].company_id != drafter.company_id:
        raise _InvalidAnswer("an attribute is taught on a concept of the taught company only")


def _plan_attr(
    c: _Checked,
    handles: list[Concept],
    sent: set[uuid.UUID],
    drafter: Drafter,
    text: str,
    taught: dict[tuple[str, str], str],
    offset: int,
) -> PlannedIntent | UnresolvedReason | None:
    """The planned attribute of an attr intent; the reason it is not drafted; or None for a
    repeat of an attribute the same answer already drafts with the same value.

    The subject resolves to a sent candidate, to a concept an earlier intent introduces, or to
    an existing concept of the taught company named in the caller's words; the name and the
    value are grounded in the caller's words inside the intent's source range."""
    intent = c.intent
    assert intent.attribute_name is not None and intent.attribute_value is not None
    subject = _attr_subject(intent.subject, handles, sent, drafter, text, c.source)
    name = _ground_name(intent.attribute_name, text, c.source)
    value = _ground_value(intent.attribute_value, text, c.source)
    if subject is None or name is None or value is None:
        return "ungrounded_label"
    if intent.confidence < MIN_CONFIDENCE:
        return "low_confidence"
    concept = subject.concept
    key = (str(concept.id) if concept else subject.label.lower(), name)
    existing = drafter.view.attribute_named(concept.id, name) if concept else None
    held = existing.value if existing is not None else None
    if existing is not None and (held is None or held.casefold() != value.casefold()):
        return "attribute_exists"
    if key in taught:
        return None if taught[key].casefold() == value.casefold() else "attribute_exists"
    span = (c.source[0] + offset, c.source[1] + offset)
    note = DraftNote(
        extractor="llm",
        confidence=intent.confidence,
        explanation=intent.explanation,
        segment=c.segment,
        source_span=SourceSpan(start=span[0], end=span[1]),
    )
    planned = drafter.model_attr(subject, name, value, intent.value_type or "text", note, held)
    if held is None:
        taught[key] = value
    planned.span = intent.span
    planned.segment = c.segment
    return planned


def _attr_subject(
    ref: Any,
    handles: list[Concept],
    sent: set[uuid.UUID],
    drafter: Drafter,
    text: str,
    source: tuple[int, int],
) -> End | None:
    """The concept an attr intent describes, or None. A new label is reused as a candidate sent
    in this call, else names a concept an earlier intent of the answer introduces, else must be
    grounded in the caller's words and then name an existing concept of the taught company; it
    never introduces a concept."""
    if isinstance(ref, CandidateRef):
        concept = handles[int(ref.candidate[1:])]
        return End(concept, concept.label, concept.label)
    label = title(unicodedata.normalize("NFKC", ref.new_label))
    reused = drafter.resolve(label)
    if reused is not None and reused.id in sent:
        return End(reused, reused.label, reused.label)
    introduced = drafter.introduced_label(label)
    if introduced is not None:
        return End(None, introduced, introduced, cited_new=True)
    spoken = _ground(label, text, source)
    concept = drafter.resolve(spoken) if spoken else None
    if concept is None or spoken is None:
        return None
    return End(concept, concept.label, spoken)


def _ground_value(value: str, text: str, source: tuple[int, int]) -> str | None:
    """The caller's own words in `text[source]` that `value` quotes, word for word (NFKC and
    case folded, no singular or plural), sliced from the input with its whitespace runs
    collapsed; None when the input does not carry them."""
    for first, last in _runs(value, text, source, _fold_exact):
        spoken = " ".join(unicodedata.normalize("NFKC", text[first:last]).split())
        if 0 < len(spoken) <= MAX_ATTRIBUTE_VALUE and not has_refused_character(spoken):
            return spoken
    return None


def _ground_name(name: str, text: str, source: tuple[int, int]) -> str | None:
    """`name` lower-cased when each of its words is a word of `text[source]` or an inflection
    of one (see `_inflects`: `billing` for `billed`, `base` for `based`), else None. The name is
    words separated by single spaces, nothing else."""
    start, end = source
    words = _words(text)
    if any(a < start < b or a < end < b for a, b in words):
        return None
    spoken = [_fold_exact(text[a:b]) for a, b in words if a >= start and b <= end]
    normalised = unicodedata.normalize("NFKC", name).casefold()
    name_words = [normalised[a:b] for a, b in _words(normalised)]
    if not name_words or " ".join(name_words) != normalised:
        return None
    if len(normalised) > MAX_ATTRIBUTE_NAME or has_refused_character(normalised):
        return None
    if any(not any(_inflects(w, said) for said in spoken) for w in name_words):
        return None
    return normalised


def _inflects(a: str, b: str) -> bool:
    """True when `a` and `b` are the same word, when one is the other plus an allowed suffix
    (`base` and `based`), or when both are one stem of at least four characters plus an
    allowed suffix each (`billed` and `billing`). A shorter shared stem is not enough, so
    `rats` and `rated` or `bass` and `based` differ."""
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    if len(short) >= _MIN_STEM and any(long == short + suffix for suffix in _INFLECTIONS):
        return True
    return bool(_stems(a) & _stems(b))


def _stems(word: str) -> set[str]:
    """The stems `word` gives with one allowed suffix removed, each at least
    `_MIN_SHARED_STEM` characters long."""
    return {
        word[: -len(suffix)]
        for suffix in _INFLECTIONS
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_SHARED_STEM
    }


def _fold_exact(word: str) -> str:
    return unicodedata.normalize("NFKC", word).casefold()


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
