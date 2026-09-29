"""Document sentences keep every word: headings, list items and table rows end at their line
break, wrapped lines join, and a long sentence is cut at a clause boundary, never dropped."""

from __future__ import annotations

import re
import time

from app.utilities.document_text import (
    MAX_SENTENCE_CHARS,
    MIN_SENTENCE_CHARS,
    TEXT_MARKDOWN,
    extract_sentences,
    sentences_of,
    split_sentences,
)

LONG_CLAUSE = (
    "Insight delivers managed data platforms for energy clients across the region, "
    "and each platform is run by a dedicated team that owns ingestion, quality and reporting"
)
LONG = "; ".join([LONG_CLAUSE] * 6) + ", including a service desk that answers every day."

DOCUMENT = f"""# Insight Services Overview

Insight sells services to large energy companies
in the Gulf region and in Europe. The services are
grouped into three practices.

## Practices and Their Offers

- Data practice builds platforms
- AI practice trains assistants
* Apps practice ships portals

1. First, the client describes its needs.
2. Then Insight proposes a delivery team.

| Client name | Relationship |
|---|---|
| ADNOC Drilling | Strategic client |
| TotalEnergies SE | Pilot client |

{LONG}
"""


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text)


def nonblank(pieces: list[str]) -> str:
    """The pieces' characters without whitespace, which a cut may drop or a join may add."""
    return re.sub(r"\s", "", "".join(pieces))


def test_every_word_of_a_structured_document_is_kept_in_order() -> None:
    assert len(LONG) > 900

    sentences = sentences_of(DOCUMENT)

    assert words(" ".join(sentences)) == words(DOCUMENT)
    assert all(MIN_SENTENCE_CHARS <= len(s) <= MAX_SENTENCE_CHARS for s in sentences)
    assert sentences[:4] == [
        "# Insight Services Overview",
        "Insight sells services to large energy companies in the Gulf region and in Europe.",
        "The services are grouped into three practices.",
        "## Practices and Their Offers",
    ]
    assert "- Data practice builds platforms" in sentences
    assert "* Apps practice ships portals" in sentences
    assert "2. Then Insight proposes a delivery team." in sentences
    assert "| ADNOC Drilling | Strategic client |" in sentences


def test_a_long_sentence_is_cut_after_a_clause_boundary() -> None:
    pieces = sentences_of(LONG)

    assert " ".join(pieces) == LONG
    assert len(pieces) > 2
    assert all(p.endswith(";") for p in pieces[:-1])


def test_a_long_run_without_clauses_or_spaces_is_cut_and_kept() -> None:
    commas = ", ".join(["alpha beta gamma delta"] * 40) + "."
    solid = "x" * 900

    assert " ".join(sentences_of(commas)) == commas
    assert "".join(sentences_of(solid)) == solid
    assert all(len(p) <= MAX_SENTENCE_CHARS for p in sentences_of(commas) + sentences_of(solid))


def test_positions_follow_the_document() -> None:
    sentences, extracted, skipped = extract_sentences(DOCUMENT.encode(), TEXT_MARKDOWN)

    assert extracted == len(DOCUMENT)
    assert [s.text for s in sentences] == sentences_of(DOCUMENT)
    assert all(s.unit is None and s.index is None for s in sentences)
    assert skipped == 0


def test_short_pieces_are_counted_as_skipped() -> None:
    kept, skipped = split_sentences("# Clients\n\n- ADNOC\n- TotalEnergies SE Group\n|---|---|\n")

    assert kept == ["- TotalEnergies SE Group"]
    assert skipped == 2


def test_a_cut_never_leaves_a_tail_too_short_to_keep() -> None:
    sentence = "a" * 396 + "; " + "b" * 12

    kept, skipped = split_sentences(sentence)

    assert skipped == 0
    assert nonblank(kept) == nonblank([sentence])
    assert all(MIN_SENTENCE_CHARS <= len(p) <= MAX_SENTENCE_CHARS for p in kept)


def test_a_cut_at_every_length_near_the_limit_loses_no_text() -> None:
    for tail in range(1, 40):
        for sentence in ("a" * 396 + "; " + "b" * tail, "a" * 396 + " " + "b" * tail):
            kept, skipped = split_sentences(sentence)

            assert skipped == 0, sentence
            assert nonblank(kept) == nonblank([sentence])


def test_a_two_million_character_block_without_line_breaks_splits_quickly() -> None:
    block = ("word " * 400_000).strip()

    started = time.perf_counter()
    kept, skipped = split_sentences(block)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert skipped == 0
    assert " ".join(kept) == block
