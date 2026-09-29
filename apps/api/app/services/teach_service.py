"""`POST /teach/parse`: one sentence to intents and proposal drafts, writing nothing to the model.

The sentence is typed text, a speech transcript, or a stored import sentence cited by
`importRef`, whose text is read from the import. Every path runs the same grammar and resolves
the names it finds against the company's current concepts, pending ones included; a name that
resolves to nothing becomes a proposed new cell, never a silent creation.

When a fallback trigger holds, the language model step runs after the grammar. A valid answer
replaces the grammar's intents, or is merged into them when only `partly_understood` triggered
the step; any other end of the step leaves the grammar's result standing, marked `degraded`,
with the whole sentence listed as unresolved. The sentence is then stored as a turn of the
caller's teach session.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.config import LlmProfile
from app.models.api.origin import ImportRef
from app.models.api.teach import (
    SourceSegment,
    SourceSpan,
    TeachRequest,
    TeachResult,
    UnresolvedPhrase,
)
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
DOCUMENT_CONTEXT_SENTENCES = 2


@dataclass(frozen=True)
class _Source:
    text: str
    origin: str
    origin_detail: dict[str, Any] | None
    draft_extras: dict[str, Any]
    reading: Reading = Reading()
    # Typed text and speech run on the `live` model profile; document sentences on `deep`.
    profile: LlmProfile = "live"


async def parse(session: AsyncSession, caller: Caller, body: TeachRequest) -> TeachResult:
    view = await load_view(session, caller.tenant_id)
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
    speech = source.reading.speech
    root = view.root_of(company.id)
    if root is None:
        empty = Assembled([], [], [], [], [], [], [])
        result = _result("rules", "not_triggered", empty, None, NOT_UNDERSTOOD, source, [])
        await teach_session_service.store_turn(key, sentence, "rules", [], [])
        return result
    dom_key, text = domain_prefix(sentence)
    drafter = Drafter(view, company.id, root, dom_key, source.draft_extras)
    whole = [(0, len(sentence))]
    grammar: GrammarPlan | None = None
    triggers: set = set()
    # Every origin goes to the model first while the step is on; typed text keeps the grammar
    # and its fallback triggers for when the step is off or does not answer.
    model_first = source.reading.model_first or teach_extraction_service.enabled(
        view, source.profile
    )
    if not source.reading.model_first:
        grammar = plan_grammar(drafter, text)
        triggers = fallback_triggers(text, grammar.outcome)
    if grammar is not None and not triggers and not model_first:
        kept = assemble(grammar.planned, sentence)
        caption = grammar.caption
        result = _result("rules", "not_triggered", kept, dom_key, caption, source, whole)
    else:
        # The request's own transaction ends here, so it holds no lock during the model call.
        await session.commit()
        turns = await teach_session_service.recent_turns(key)
        step = await teach_extraction_service.run(
            caller, drafter, sentence, text, turns, source.reading, profile=source.profile
        )
        if step.outcome != "used":
            if speech:
                grammar, segments = _grammar_by_segment(drafter, sentence)
            else:
                grammar, segments = grammar or plan_grammar(drafter, text), whole
            if grammar is not None and not triggers and not source.reading.model_first:
                # Typed text the grammar reads whole: its result stands as it would with the
                # step off, and the outcome says why the model did not answer.
                kept = assemble(grammar.planned, sentence)
                caption = grammar.caption
                result = _result("rules", step.outcome, kept, dom_key, caption, source, whole)
            else:
                result, kept = _degraded(grammar, step, segments, sentence, dom_key, source)
        else:
            replace = model_first or replaces_grammar(triggers)
            segments = step.segments or whole
            result, kept = _with_model(grammar, step, replace, sentence, dom_key, source, segments)
    await teach_session_service.store_turns(key, result.extractor, _turns(source, result, kept))
    return result


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
