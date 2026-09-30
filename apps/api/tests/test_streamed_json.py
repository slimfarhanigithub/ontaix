"""Whole items of a JSON object whose text is still arriving."""

from __future__ import annotations

import json

import pytest

from app.utilities.streamed_json import closed_items
from tests.llm_fakes import FIXTURES, recorded

NAMES = sorted(p.stem for p in FIXTURES.glob("*.json"))


@pytest.mark.parametrize("name", NAMES)
def test_every_prefix_of_a_recorded_answer_gives_a_prefix_of_its_items(name: str) -> None:
    text = recorded(name)
    whole = json.loads(text)
    counts = {key: 0 for key in whole}

    for end in range(len(text) + 1):
        items = closed_items(text[:end])
        for key, got in items.items():
            assert got == whole[key][: len(got)]
            assert len(got) >= counts[key]
            counts[key] = len(got)

    final = closed_items(text)
    for key, value in whole.items():
        if isinstance(value, list):
            assert final[key] == value


def test_braces_brackets_and_quotes_inside_strings_do_not_close_an_item() -> None:
    first = {"span": 'a } b " { ] c', "note": "\\"}
    text = json.dumps({"intents": [first, {"x": [1, {"y": 2}]}]})
    cut = text.index('{"x"') + 3

    assert closed_items(text[:cut]) == {"intents": [first]}
    assert closed_items(text) == {"intents": [first, {"x": [1, {"y": 2}]}]}


def test_fragments_split_anywhere_give_the_same_items() -> None:
    text = recorded("speech_insight_transcript")
    received = ""
    seen: list[int] = []
    for i in range(0, len(text), 7):
        received += text[i : i + 7]
        seen.append(len(closed_items(received).get("intents", [])))

    assert seen == sorted(seen)
    assert seen[-1] == len(json.loads(text)["intents"])


def test_other_values_and_broken_text_give_no_items() -> None:
    assert closed_items("") == {}
    assert closed_items("[1, 2]") == {}
    assert closed_items('{"segments": null, "intents": [') == {"intents": []}
    assert closed_items('{"a": {"b": [{"c": 1}]}}') == {}
    assert closed_items('{"intents": [{"a": 1}, {"b": ,}]}') == {"intents": [{"a": 1}]}
