"""`POST /teach/parse`: one sentence to intents and proposal drafts, writing nothing to the model.

The sentence is typed text, a speech transcript, or a stored import sentence cited by
`importRef`, whose text is read from the import. Every path runs the same grammar and resolves
the names it finds against the company's current concepts, pending ones included; a name that
resolves to nothing becomes a proposed new cell, never a silent creation.

When a fallback trigger holds, the language model step runs after the grammar. A valid answer
replaces the grammar's intents, or is merged into them when only `partly_understood` triggered
the step. When the step is on and does not answer, or its answer is refused, typed text and
speech draft nothing: the result is `not_understood`, marked `degraded`, with every segment
listed as unresolved. Document sentences, and every origin while the step is off, keep the
grammar's result, marked `degraded` when the step was needed. The sentence is then stored as a
turn of the caller's teach session.

A parse runs in two parts: `prepare` applies the gates and charges, so every refusal is raised
before any answer begins, and runs the grammar; `PreparedParse.finish` runs the model step and
stores the turns. The streamed variant passes a listener to `finish`, which receives the
grammar's drafts at once when the grammar read a typed sentence whole, then the drafts of each
valid part of the model's answer as it arrives; the result is the same either way.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.config import LlmProfile
from app.models.api.origin import ImportRef
from app.models.api.teach import (
    DraftNote,
    SourceSegment,
    SourceSpan,
    TeachRequest,
    TeachResult,
    UnresolvedPhrase,
)
from app.repositories.teach_session_turn_repository import SessionKey
from app.services import import_service, teach_extraction_service, teach_session_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import Budget, charge
from app.services.teach_draft_service import (
    MAX_INTENTS,
    MAX_TRANSCRIPT_INTENTS,
    MAX_TRANSCRIPT_UNRESOLVED,
    MAX_UNRESOLVED,
    NOT_UNDERSTOOD,
    Assembled,
    Drafter,
    GrammarPlan,
    PlannedIntent,
    add_unresolved,
    assemble,
    caption_for,
    new_labels,
    phrase_in,
    plan_grammar,
)
from app.services.teach_extraction_service import Reading
from app.utilities.channels import (
    ensure_import_allowed,
    ensure_live_teaching_allowed,
    ensure_speech_allowed,
)
from app.utilities.permissions import can_propose_anywhere, can_read
from app.utilities.problems import forbidden, not_found
from app.utilities.teach_parser import domain_prefix
from app.utilities.teach_triggers import fallback_triggers, replaces_grammar
from app.utilities.transcript import MAX_SEGMENTS, split_transcript

logger = logging.getLogger(__name__)

PARSE_UNIT_CHARS = 400
# Ends of a model step that is on but did not answer.
UNAVAILABLE = frozenset({"rate_limited", "budget_exhausted", "timeout", "provider_error"})
DOCUMENT_CONTEXT_SENTENCES = 2
# Bounds on the grammar's drafts shown while the model answers.
MAX_INSTANT_DRAFTS = 6
MAX_INSTANT_LABEL_WORDS = 4
_NOT_IN_A_CONCEPT_NAME = frozenset(
    {
        "that",
        "which",
        "who",
        "whose",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "and",
        "or",
        "but",
        "also",
        "too",
        "including",
        "with",
        "into",
        "against",
        "each",
        "them",
        "they",
        "it",
        "these",
        "those",
        "this",
    }
)


# Receives the drafts, with their notes, that the part of the model's answer received so far
# gives; see `PreparedParse.finish`.
DraftListener = Callable[[list[dict[str, Any]], list[DraftNote]], Awaitable[None]]


@dataclass(frozen=True)
class _Source:
    text: str
    origin: str
    origin_detail: dict[str, Any] | None
    draft_extras: dict[str, Any]
    reading: Reading = Reading()
    # Typed text and speech run on the `live` model profile; document sentences on `deep`.
    profile: LlmProfile = "live"


@dataclass
class PreparedParse:
    """A parse whose gates, charges and grammar have run, so every refusal of the request has
    been raised; `finish` runs the rest - the model step, when one is needed - and stores the
    sentence as turns of the caller's teach session. It holds no database session."""

    caller: Caller
    source: _Source
    key: SessionKey | None
    sentence: str
    started: float
    view_ms: int
    # The result and what it kept, when they are known without the model step.
    ready: tuple[TeachResult, Assembled] | None = None
    drafter: Drafter | None = None
    dom_key: str | None = None
    text: str = ""
    grammar: GrammarPlan | None = None
    triggers: set = field(default_factory=set)
    model_first: bool = False
    step_on: bool = False

    async def finish(self, on_drafts: DraftListener | None = None) -> TeachResult:
        """The parse result. With `on_drafts` the model's answer is streamed, and each part of
        it that reads validly is mapped to the drafts the result would hold if the answer ended
        there, which go to `on_drafts`; the result is the same with or without it."""
        if self.ready is not None:
            result, kept = self.ready
        else:
            result, kept = await self._with_model_step(on_drafts)
        turns = _turns(self.source, result, kept)
        await teach_session_service.store_turns(self.key, result.extractor, turns)
        logger.debug(
            "teach parse (%s, %s): view %d ms, total %d ms",
            result.extractor,
            result.llm_outcome,
            self.view_ms,
            int((time.perf_counter() - self.started) * 1000),
        )
        return result

    async def _with_model_step(
        self, on_drafts: DraftListener | None
    ) -> tuple[TeachResult, Assembled]:
        assert self.drafter is not None
        source, sentence, drafter = self.source, self.sentence, self.drafter
        dom_key, text, triggers = self.dom_key, self.text, self.triggers
        speech = source.reading.speech
        whole = [(0, len(sentence))]
        turns = await teach_session_service.recent_turns(self.key)
        on_partial = None
        if on_drafts is not None:
            listener = on_drafts
            instant = _instant(self.grammar, triggers, sentence)
            if instant is not None:
                # The grammar read the sentence whole, nothing marks its reading as suspect and
                # its drafts look like concepts: they show at once while the model answers, and
                # the model's result replaces them. They are never proposed in the model's place.
                await listener(instant.drafts, instant.notes)

            async def on_partial(step: teach_extraction_service.ModelStep) -> None:
                result, _ = self._used(step)
                await listener(result.drafts, result.draft_notes)

        step = await teach_extraction_service.run(
            self.caller,
            drafter,
            sentence,
            text,
            turns,
            source.reading,
            profile=source.profile,
            on_partial=on_partial,
        )
        if step.outcome == "used":
            return self._used(step)
        if speech:
            grammar, segments = _grammar_by_segment(drafter, sentence)
        else:
            grammar, segments = self.grammar or plan_grammar(drafter, text), whole
        refused = source.reading.mode != "document" and (
            step.outcome == "invalid_output" or (self.step_on and step.outcome in UNAVAILABLE)
        )
        if refused:
            # The model is on and its answer was refused, or it did not answer: typed and
            # spoken text draft nothing in its place, so word runs never become labels, and
            # every segment is listed with the reason. The owner can send the sentence again.
            grammar = GrammarPlan([], "not_understood", NOT_UNDERSTOOD, grammar.beyond)
        if not refused and not triggers and not source.reading.model_first:
            # Typed text the grammar reads whole: its result stands as it would with the
            # step off, and the outcome says why the model did not answer.
            kept = assemble(grammar.planned, sentence)
            caption = grammar.caption
            return _result("rules", step.outcome, kept, dom_key, caption, source, whole), kept
        return _degraded(grammar, step, segments, sentence, dom_key, source)

    def _used(self, step: teach_extraction_service.ModelStep) -> tuple[TeachResult, Assembled]:
        """The result of a model step that answered validly, whole or in part."""
        replace = self.model_first or replaces_grammar(self.triggers)
        segments = step.segments or [(0, len(self.sentence))]
        return _with_model(
            self.grammar, step, replace, self.sentence, self.dom_key, self.source, segments
        )


def _instant(grammar: GrammarPlan | None, triggers: set, sentence: str) -> Assembled | None:
    """The grammar's drafts to show while the model answers, or None: only a typed sentence the
    grammar understood whole with no fallback trigger, giving at most MAX_INSTANT_DRAFTS drafts
    whose labels read as concept names (at most MAX_INSTANT_LABEL_WORDS words, none of them a
    word that betrays a clause or a verb list read as a name, such as `that`, `also` or
    `including`). A preview the model does not confirm fades; a wrong one costs a fading cell,
    so the gate errs on showing nothing."""
    if grammar is None or grammar.outcome != "understood" or triggers:
        return None
    assembled = assemble(grammar.planned, sentence)
    if not assembled.drafts or len(assembled.drafts) > MAX_INSTANT_DRAFTS:
        return None
    for draft in assembled.drafts:
        labels = [draft.get(key) for key in ("label", "aLabel", "bLabel", "parentLabel")]
        for label in (str(value) for value in labels if value):
            words = label.split()
            if len(words) > MAX_INSTANT_LABEL_WORDS or any(
                w.lower() in _NOT_IN_A_CONCEPT_NAME for w in words
            ):
                return None
    return assembled


async def parse(session: AsyncSession, caller: Caller, body: TeachRequest) -> TeachResult:
    prepared = await prepare(session, caller, body)
    return await prepared.finish()


async def prepare(session: AsyncSession, caller: Caller, body: TeachRequest) -> PreparedParse:
    """Everything of a parse up to the model step: the gates and charges, which raise the
    request's refusals, and the grammar. The request's own transaction is committed when the
    model step follows, so it holds no lock during the model call."""
    started = time.perf_counter()
    view = await load_view(session, caller.tenant_id)
    view_ms = int((time.perf_counter() - started) * 1000)
    company = view.companies.get(body.company_id)
    if company is None or not can_read(caller.grants, company.id):
        raise not_found("company")
    if not can_propose_anywhere(caller.grants, caller.everyone_teaches):
        raise forbidden("Your roles do not allow proposing")
    source = await _source(session, caller, view, body)
    key = (
        teach_session_service.session_key(caller, company.id, body.session_id)
        if body.session_id
        else None
    )
    sentence = source.text.strip()
    prepared = PreparedParse(caller, source, key, sentence, started, view_ms)
    root = view.root_of(company.id)
    if root is None:
        empty = Assembled([], [], [], [], [], [], [])
        result = _result("rules", "not_triggered", empty, None, NOT_UNDERSTOOD, source, [])
        prepared.ready = (result, empty)
        return prepared
    dom_key, text = domain_prefix(sentence)
    drafter = Drafter(view, company.id, root, dom_key, source.draft_extras)
    grammar: GrammarPlan | None = None
    triggers: set = set()
    # Every origin goes to the model first while the step is on; typed text keeps the grammar
    # and its fallback triggers for when the step is off or does not answer.
    step_on = teach_extraction_service.enabled(view, source.profile)
    model_first = source.reading.model_first or step_on
    if not source.reading.model_first:
        grammar = plan_grammar(drafter, text)
        triggers = fallback_triggers(text, grammar.outcome)
    if grammar is not None and not triggers and not model_first:
        kept = assemble(grammar.planned, sentence)
        whole = [(0, len(sentence))]
        caption = grammar.caption
        result = _result("rules", "not_triggered", kept, dom_key, caption, source, whole)
        prepared.ready = (result, kept)
        return prepared
    await session.commit()
    prepared.drafter, prepared.dom_key, prepared.text = drafter, dom_key, text
    prepared.grammar, prepared.triggers, prepared.model_first = grammar, triggers, model_first
    prepared.step_on = step_on
    return prepared


async def _source(
    session: AsyncSession, caller: Caller, view: OntologyView, body: TeachRequest
) -> _Source:
    """The sentence and its provenance; applies the channel gates and the charges."""
    if body.import_ref is not None:
        ensure_import_allowed(view.settings)
        return await _cited_sentence(session, caller, body.import_ref)
    ensure_live_teaching_allowed(view.settings)
    origin = body.origin or "text"
    if origin == "speech":
        ensure_speech_allowed(view.settings)
    assert body.text is not None
    # One parse unit per started 400 characters: one for a typed sentence, up to 10 for a
    # transcript.
    units = max(1, -(-len(body.text) // PARSE_UNIT_CHARS))
    await charge(Budget.PARSE, caller.tenant_id, caller.actor_kind.value, caller.user_id, units)
    reading = Reading("speech") if origin == "speech" else Reading()
    return _Source(body.text, origin, None, {"origin": origin}, reading, "live")


async def _cited_sentence(session: AsyncSession, caller: Caller, ref: ImportRef) -> _Source:
    """A stored sentence: its parse is counted, and paid for when the import was made."""
    row = await import_service.owned_import(session, caller, ref.import_id)
    sentence = await import_service.claim_parse(session, caller, row, ref.sentence_index)
    before, after = await import_service.neighbours(
        session, row, ref.sentence_index, DOCUMENT_CONTEXT_SENTENCES
    )
    return _Source(
        sentence.text,
        "document",
        import_service.origin_detail(row, ref.sentence_index, sentence),
        {"importRef": ref.model_dump(mode="json", by_alias=True)},
        Reading("document", before, after),
        "deep",
    )


def _degraded(
    grammar: GrammarPlan,
    step: teach_extraction_service.ModelStep,
    segments: list[tuple[int, int]],
    sentence: str,
    dom_key: str | None,
    source: _Source,
) -> tuple[TeachResult, Assembled]:
    """The grammar's result when the model step did not contribute; every segment of the
    sentence is listed as unresolved with the reason."""
    speech = source.reading.speech
    rules = assemble(grammar.planned, sentence, _cap(speech))
    reason = "model_invalid_output" if step.outcome == "invalid_output" else "model_unavailable"
    # The phrase for the rest of a long transcript always keeps its place under the cap.
    room = _unresolved_cap(speech) - (1 if grammar.beyond else 0)
    for start, end in segments:
        phrase = UnresolvedPhrase(text=sentence[start:end][:400], reason=reason)
        add_unresolved(rules.unresolved, phrase, room)
    if grammar.beyond:
        phrase = UnresolvedPhrase(text=grammar.beyond, reason="too_many_segments")
        add_unresolved(rules.unresolved, phrase, _unresolved_cap(speech))
    result = _result("rules", step.outcome, rules, dom_key, grammar.caption, source, segments, True)
    return result, rules


def _with_model(
    grammar: GrammarPlan | None,
    step: teach_extraction_service.ModelStep,
    replace: bool,
    sentence: str,
    dom_key: str | None,
    source: _Source,
    segments: list[tuple[int, int]],
) -> tuple[TeachResult, Assembled]:
    if replace or grammar is None:
        planned, extractor = step.planned, "llm"
    else:
        known = {p.identity for p in grammar.planned}
        added: list[PlannedIntent] = []
        for p in step.planned:
            if p.identity not in known:
                known.add(p.identity)
                added.append(p)
        planned = [*grammar.planned, *added]
        extractor = "rules+llm" if added else "rules"
    speech = source.reading.speech
    merged = assemble(planned, sentence, _cap(speech))
    for phrase in step.unresolved:
        add_unresolved(merged.unresolved, phrase, _unresolved_cap(speech))
    if not merged.intents and not merged.unresolved:
        whole = UnresolvedPhrase(text=phrase_in(sentence, None), reason="not_understood")
        add_unresolved(merged.unresolved, whole, _unresolved_cap(speech))
    if extractor == "rules" and grammar is not None:
        caption = grammar.caption
    elif merged.statements:
        caption = caption_for(merged.kept)
    else:
        caption = NOT_UNDERSTOOD
    return _result(extractor, "used", merged, dom_key, caption, source, segments), merged


def _grammar_by_segment(
    drafter: Drafter, sentence: str
) -> tuple[GrammarPlan, list[tuple[int, int]]]:
    """The grammar over a transcript split into segments, each parsed on its own."""
    segments = split_transcript(sentence)
    kept, rest = segments[:MAX_SEGMENTS], segments[MAX_SEGMENTS:]
    segments = kept
    planned: list[PlannedIntent] = []
    for i, (start, end) in enumerate(segments):
        dom_key, text = domain_prefix(sentence[start:end])
        segment_drafter = Drafter(
            drafter.view, drafter.company_id, drafter.root, dom_key, drafter.extras
        )
        for p in plan_grammar(segment_drafter, text).planned:
            p.segment = i
            p.note = p.note.model_copy(update={"segment": i})
            planned.append(p)
    statements = [line for p in planned for line in p.statements]
    beyond = sentence[rest[0][0] :][:400] if rest else None
    if statements:
        return GrammarPlan(planned, "understood", caption_for(planned), beyond), segments
    return GrammarPlan(planned, "not_understood", NOT_UNDERSTOOD, beyond), segments


def _cap(speech: bool) -> int:
    return MAX_TRANSCRIPT_INTENTS if speech else MAX_INTENTS


def _unresolved_cap(speech: bool) -> int:
    return MAX_TRANSCRIPT_UNRESOLVED if speech else MAX_UNRESOLVED


def _result(
    extractor: str,
    llm_outcome: str,
    assembled: Assembled,
    dom_key: str | None,
    caption: str,
    source: _Source,
    segments: list[tuple[int, int]],
    degraded: bool = False,
) -> TeachResult:
    if not assembled.intents:
        outcome = "not_understood"
    elif assembled.unresolved:
        outcome = "partly_understood"
    else:
        outcome = "understood"
    # Offsets are computed on the trimmed input and returned relative to the caller's original
    # input, leading whitespace included.
    lead = len(source.text) - len(source.text.lstrip())
    notes = [
        n.model_copy(
            update={
                "source_span": SourceSpan(
                    start=n.source_span.start + lead, end=n.source_span.end + lead
                )
            }
        )
        if n.source_span is not None
        else n
        for n in assembled.notes
    ]
    return TeachResult(
        outcome=outcome,
        domain_key=dom_key,
        intents=assembled.intents,
        drafts=assembled.drafts,
        statements=assembled.statements,
        caption=caption,
        origin=source.origin,
        origin_detail=source.origin_detail,
        extractor=extractor,
        degraded=degraded,
        llm_outcome=llm_outcome,
        draft_notes=notes,
        unresolved=assembled.unresolved,
        segments=[
            SourceSegment(index=i, span=SourceSpan(start=start + lead, end=end + lead))
            for i, (start, end) in enumerate(segments)
        ],
    )


def _turns(
    source: _Source, result: TeachResult, assembled: Assembled
) -> list[tuple[str, list[uuid.UUID], list[str]]]:
    """The session turns a parse stores: one per segment, in order, each with the concepts it
    referenced and the labels it introduced."""
    original = source.text
    turns: list[tuple[str, list[uuid.UUID], list[str]]] = [
        (original[s.span.start : s.span.end], [], []) for s in result.segments
    ] or [(original.strip(), [], [])]
    for planned in assembled.kept:
        _, ids, labels = turns[min(planned.segment, len(turns) - 1)]
        ids.extend(i for i in planned.concept_ids if i not in ids)
        labels.extend(label for label in new_labels(planned.drafts) if label not in labels)
    return turns
