"""What a bake-off plan will cost before anything runs.

Calls per case: one per typed turn (an upper bound: the grammar answers some turns alone), one
per transcript, one per stored sentence of a document (counted with the API's own sentence
splitter), and one per 3,000 words in whole-document mode. Tokens per call: the fixed system
prompt and output schema, the unit's text, and the context the API sends with it (session
turns, and for documents the neighbours and the candidate concepts, which grow as a document is
taught, up to 200). Output: the answer, plus the reasoning tokens a model spends at each effort.
These per-call figures are deliberately on the high side; the screening stage's measured tokens
replace them for the finals.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from pypdf import PdfReader

from app.ai.prompts.teach_extraction import OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.utilities.document_text import MEDIA_TYPE_BY_EXTENSION, TEXT_PLAIN, extract_sentences
from evals.candidate import RunConfig
from evals.doc_formats.loader import DocumentFormatError
from evals.input_modes import DocumentCache
from evals.teach_case import TeachCase

CHARS_PER_TOKEN = 3.5
SESSION_CONTEXT_TOKENS = 250
NEIGHBOUR_TOKENS = 120
CANDIDATE_TOKENS = 25
MAX_CANDIDATES = 200
CONCEPTS_PER_SENTENCE = 0.8
ANSWER_TOKENS = {"text": 300, "speech": 1800, "document": 300}
REASONING_TOKENS = {
    "default": 300,
    "none": 0,
    "minimal": 200,
    "low": 900,
    "medium": 2500,
    "high": 6000,
}
WHOLE_DOCUMENT_WORDS_PER_CALL = 3000
SCANNED_SENTENCES_PER_PAGE = 25


@dataclass
class CaseLoad:
    """The model calls and tokens one case costs in one mode, independent of the model."""

    case_id: str
    mode: str
    calls: int
    input_tokens: int
    answer_tokens: int
    # Pages of a scanned document, read once by OCR whatever the configuration.
    ocr_pages: int = 0


@dataclass
class Estimate:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    unpriced: list[str] = field(default_factory=list)
    by_config: dict[str, float] = field(default_factory=dict)


async def case_load(case: TeachCase, mode: str, docs: DocumentCache) -> CaseLoad:
    fixed = (len(SYSTEM_PROMPT) + len(json.dumps(OUTPUT_SCHEMA))) / CHARS_PER_TOKEN
    if case.kind == "text":
        calls = len(case.input)
        text_tokens = sum(len(t) for t in case.input) / CHARS_PER_TOKEN
        input_tokens = calls * (fixed + SESSION_CONTEXT_TOKENS) + text_tokens
        return CaseLoad(case.id, mode, calls, int(input_tokens), calls * ANSWER_TOKENS["text"])
    if case.kind == "speech":
        calls = len(case.input)
        text_tokens = sum(len(s) for s in case.input) / CHARS_PER_TOKEN
        input_tokens = calls * (fixed + SESSION_CONTEXT_TOKENS) + text_tokens
        return CaseLoad(case.id, mode, calls, int(input_tokens), calls * ANSWER_TOKENS["speech"])
    sentences, words, ocr_pages = await _document_size(case, docs)
    if mode == "whole":
        calls = max(1, math.ceil(words / WHOLE_DOCUMENT_WORDS_PER_CALL))
        input_tokens = calls * fixed + words * 1.4 + MAX_CANDIDATES * CANDIDATE_TOKENS
        answer = calls * 4 * ANSWER_TOKENS["text"]
        return CaseLoad(case.id, mode, calls, int(input_tokens), answer, ocr_pages)
    per_sentence = fixed + SESSION_CONTEXT_TOKENS + NEIGHBOUR_TOKENS + 30
    candidates = sum(min(MAX_CANDIDATES, int(i * CONCEPTS_PER_SENTENCE)) for i in range(sentences))
    input_tokens = sentences * per_sentence + candidates * CANDIDATE_TOKENS
    answer = sentences * ANSWER_TOKENS["document"]
    return CaseLoad(case.id, mode, sentences, int(input_tokens), answer, ocr_pages)


def estimate(plan: list[tuple[RunConfig, CaseLoad, int]]) -> Estimate:
    """The cost of running each load under its configuration the given number of times."""
    out = Estimate()
    for config, load, repeats in plan:
        output = load.answer_tokens + load.calls * REASONING_TOKENS[config.effort]
        out.calls += load.calls * repeats
        out.input_tokens += load.input_tokens * repeats
        out.output_tokens += output * repeats
        if config.price is None:
            if config.deployment not in out.unpriced:
                out.unpriced.append(config.deployment)
            continue
        eur = (
            float(config.price.input_eur_per_mtok) * load.input_tokens
            + float(config.price.output_eur_per_mtok) * output
        ) / 1_000_000
        out.cost_eur += eur * repeats
        out.by_config[config.key] = out.by_config.get(config.key, 0.0) + eur * repeats
    return out


async def _document_size(case: TeachCase, docs: DocumentCache) -> tuple[int, int, int]:
    """Stored sentences, words and scanned pages of a document, as the import would split it.
    `docs` must have no OCR client: a scanned PDF is sized from its page count, unread."""
    if case.document is None:
        body = case.input[0].encode("utf-8")
        sentences, _, _ = extract_sentences(body, TEXT_PLAIN)
        return len(sentences), len(case.input[0].split()), 0
    try:
        loaded = await docs.get(case.document)
    except DocumentFormatError:
        if case.document.suffix.lower() != ".pdf":
            raise
        pages = len(PdfReader(str(case.document)).pages)
        sentences = pages * SCANNED_SENTENCES_PER_PAGE
        return sentences, sentences * 20, pages
    media = MEDIA_TYPE_BY_EXTENSION.get("." + loaded.upload_name.rsplit(".", 1)[-1].lower())
    sentences, _, _ = extract_sentences(loaded.upload_bytes, media or TEXT_PLAIN)
    return len(sentences), loaded.words, 0
