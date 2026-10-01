"""A language model client for a dry run of the bake-off: no network, always a valid answer.

It reads the call's data like a model would, takes the first sentence of the text as one
segment, and answers that the company root `has` the last long word of that sentence. For a
whole-document job it answers the outline pass with one node per chunk, the last long word of
the chunk's first sentence born from the root, and the section pass with no intent. The
answer passes the pipeline's validation and grounding, so a dry run exercises the whole path
(seeding, parse, drafts, submit, scoring, cost) without measuring anything about a model.
"""

from __future__ import annotations

import json
import re

from app.clients.llm_client import LlmAnswer, LlmRequest, cost_eur, estimate_tokens
from app.config import ModelPrice

PROVIDER = "dry_run"
MAX_SEGMENT_CHARS = 300

_LONG_WORD = re.compile(r"[A-Za-z]{3,}")


class DryRunLlmClient:
    provider = PROVIDER

    def __init__(self, model: str, price: ModelPrice | None) -> None:
        self.model = model
        self._price = price

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        data = json.loads(request.user)
        if "pass" in data:
            text = _document_answer(data)
        else:
            text = _answer(data["sentence"], data["mode"] == "speech")
        tokens_in, tokens_out = estimate_tokens(request), max(1, len(text) // 4)
        cost = cost_eur(self._price, tokens_in, tokens_out) if self._price else 0.0
        return LlmAnswer(text, tokens_in, tokens_out, cost, 0)


def _answer(sentence: str, speech: bool) -> str:
    start, end = _first_sentence(sentence)
    words = _LONG_WORD.findall(sentence[start:end])
    if not words:
        phrase = sentence.strip()[:400] or "?"
        return json.dumps(
            {"intents": [], "unresolved": [{"text": phrase, "reason": "not_understood"}]}
        )
    word = words[-1]
    intent: dict = {
        "kind": "rel",
        "subject": {"candidate": "c0"},
        "object": {"newLabel": word[0].upper() + word[1:]},
        "action": "has",
        "confidence": 0.9,
        "source": {"start": start, "end": end},
        "span": sentence[start:end],
    }
    answer: dict = {"intents": [intent], "unresolved": []}
    if speech:
        intent["segment"] = 0
        answer["segments"] = [{"index": 0, "start": start, "end": end}]
    return json.dumps(answer)


def _document_answer(data: dict) -> str:
    if data["pass"] == "section":
        return json.dumps({"pass": "section", "intents": [], "unresolved": []})
    sentences = data.get("sentences") or []
    for sentence in sentences:
        words = _LONG_WORD.findall(sentence["text"])
        if words:
            word = words[-1]
            node = {
                "key": f"k{data['chunk']['number']}",
                "parent": {"handle": "c0"},
                "label": word[0].upper() + word[1:],
                "action": "has",
                "role": "entity",
                "confidence": 0.9,
                "sentenceIndex": sentence["index"],
                "span": word,
            }
            return json.dumps({"pass": "outline", "nodes": [node]})
    return json.dumps({"pass": "outline", "nodes": []})


def _first_sentence(text: str) -> tuple[int, int]:
    """The first sentence of `text` as a trimmed range of at most 300 code points, cut at a
    word boundary."""
    start = len(text) - len(text.lstrip())
    stop = text.find(".", start)
    end = stop if stop > start else len(text)
    if end - start > MAX_SEGMENT_CHARS:
        cut = text.rfind(" ", start, start + MAX_SEGMENT_CHARS)
        end = cut if cut > start else start + MAX_SEGMENT_CHARS
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, max(end, start + 1)
