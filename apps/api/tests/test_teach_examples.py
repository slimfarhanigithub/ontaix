"""Worked examples of the teach extraction prompt: the fixed prefix, retrieval, the token bound,
the validity of every example, and the learn/test split they come from."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx
import jsonschema
import pytest

from app.ai.prompts import teach_extraction
from app.ai.prompts.teach_extraction import (
    EXAMPLE_LIBRARY,
    EXAMPLES_FILE,
    FIXED_EXAMPLES,
    MAX_RETRIEVED_EXAMPLE_TOKENS,
    MAX_RETRIEVED_EXAMPLES,
    SYSTEM_PROMPT,
    render_example,
)
from app.clients.llm_client import LlmRequest, estimate_tokens
from app.models.llm.teach_extraction_answer import NewLabelRef, TeachExtractionAnswer
from app.services.teach_extraction_service import _ground, example_tokens, examples_for
from app.utilities.example_selection import most_similar, within_budget
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient, recorded
from tests.test_teach_extraction import FIRST, SECOND, add_company, configure, teach

EXAMPLES_DIR = EXAMPLES_FILE.parent
SPLIT = json.loads((EXAMPLES_DIR / "split.json").read_text(encoding="utf-8"))
CONTRACT = json.loads(
    (Path(__file__).parents[3] / "contracts" / "teach-extraction.schema.json").read_text(
        encoding="utf-8"
    )
)
# The bake-off material beside the API.
EVALS = Path(__file__).parents[1] / "evals"
ALL_EXAMPLES = [*FIXED_EXAMPLES, *EXAMPLE_LIBRARY]

QUERIES = [
    (FIRST, "sentence"),
    (SECOND, "sentence"),
    ("Our plant has three lines: pressing, painting and assembly.", "sentence"),
    ("so um the depot has a yard and uh the yard has trailer bays", "speech"),
    ("La direction commerciale gère les ventes et les ventes ont deux canaux.", "document"),
    ("Acme is a supplier of Globex that sells bearings.", "sentence"),
    ("zzz qqq", "sentence"),
    ("", "speech"),
]


def test_the_library_holds_20_to_40_examples_and_the_prompt_3_to_5() -> None:
    assert 20 <= len(EXAMPLE_LIBRARY) <= 40
    assert 3 <= len(FIXED_EXAMPLES) <= 5
    ids = [e["id"] for e in ALL_EXAMPLES]
    assert len(ids) == len(set(ids))


def test_the_system_prompt_is_the_instructions_then_the_fixed_examples() -> None:
    assert SYSTEM_PROMPT.startswith(teach_extraction._INSTRUCTIONS)
    assert SYSTEM_PROMPT == teach_extraction._INSTRUCTIONS + teach_extraction._fixed_examples_text()
    for example in FIXED_EXAMPLES:
        shown = json.dumps(example["output"], ensure_ascii=False, separators=(",", ":"))
        assert shown in SYSTEM_PROMPT


@pytest.mark.parametrize("example", ALL_EXAMPLES, ids=lambda e: e["id"])
def test_every_example_answer_is_one_the_api_accepts(example: dict) -> None:
    output = example["output"]
    jsonschema.validate(output, CONTRACT)
    answer = TeachExtractionAnswer.model_validate_json(json.dumps(output))
    text = example["input"]["sentence"]
    handles = {c["handle"] for c in example["input"]["candidates"]}
    grounded: set[str] = set()
    for intent in answer.intents:
        source = (intent.source.start, intent.source.end)
        # The quote is the input's own words at the stated offsets.
        assert text[source[0] : source[1]] == intent.span
        for ref in [intent.subject, intent.object, *(intent.members or [])]:
            if not isinstance(ref, NewLabelRef):
                assert ref.candidate in handles
                continue
            spoken = _ground(ref.new_label, text, source)
            assert spoken is not None or ref.new_label.casefold() in grounded, ref.new_label
            if spoken:
                grounded.add(spoken.casefold())
    for segment in answer.segments or []:
        assert 0 <= segment.start < segment.end <= len(text)


def test_example_selection_is_deterministic() -> None:
    for text, mode in QUERIES:
        first = examples_for(text, mode)
        assert first == examples_for(text, mode)
        assert len(first) <= MAX_RETRIEVED_EXAMPLES
    docs = ["alpha beta", "beta alpha", "gamma"]
    assert most_similar("alpha", docs) == [0, 1]
    assert most_similar("gamma alpha", docs) == [2, 0, 1]
    assert most_similar("delta", docs) == []


def test_selection_follows_the_words_and_the_mode() -> None:
    french = examples_for("Chaque commande client comporte des lignes de commande.", "sentence")
    assert french[0]["input"]["sentence"].startswith("Chaque commande client")
    speech = examples_for("so um the plant has a paint shop and uh the paint shop", "speech")
    assert speech and all(e["input"]["mode"] == "speech" for e in speech[:2])
    role = examples_for("Acme is a customer of Northbeam Consulting.", "sentence")
    assert (
        role[0]["input"]["sentence"] == "Brightline Retail is a customer of Northbeam Consulting."
    )


def test_the_retrieved_examples_stay_within_the_token_bound() -> None:
    queries = [*QUERIES, *((e["input"]["sentence"], e["input"]["mode"]) for e in EXAMPLE_LIBRARY)]
    for text, mode in queries:
        chosen = examples_for(text, mode)
        assert sum(example_tokens(e) for e in chosen) <= MAX_RETRIEVED_EXAMPLE_TOKENS
    # Every library example fits the bound on its own, so none is unreachable.
    assert all(
        example_tokens(render_example(e)) <= MAX_RETRIEVED_EXAMPLE_TOKENS for e in EXAMPLE_LIBRARY
    )
    assert within_budget([0, 1, 2, 3], [5, 9, 3, 1], limit=3, budget=10) == [0, 2, 3]
    assert within_budget([0, 1, 2], [1, 1, 1], limit=2, budget=10) == [0, 1]


def test_no_example_comes_from_test_material() -> None:
    learn = set(SPLIT["learn"]["cases"])
    test = set(SPLIT["test"]["cases"])
    assert not learn & test
    assert SPLIT["learn"]["benchmarks"] == ["goodrelations", "prov-o", "dcat"]
    assert SPLIT["test"]["benchmarks"] == ["org", "ssn", "time", "valueflows"]
    assert not set(SPLIT["learn"]["benchmarks"]) & set(SPLIT["test"]["benchmarks"])
    for example in ALL_EXAMPLES:
        source = example["source"]
        if source["set"] == "benchmark":
            assert source["id"] in SPLIT["learn"]["benchmarks"], example["id"]
        else:
            assert source["set"] in {"case", "document"}, example["id"]
            assert source["id"] in learn and source["id"] not in test, example["id"]
    text = json.dumps(ALL_EXAMPLES, ensure_ascii=False).casefold()
    for marker in ("w3.org/ns/org", "org:", "vocab-org", "tests/private"):
        assert marker not in text


def test_no_example_shares_a_phrase_with_test_material() -> None:
    import yaml

    cases = yaml.safe_load((EVALS / "cases" / "teach_cases.yaml").read_text(encoding="utf-8"))
    held_out: list[str] = []
    for case in cases["cases"]:
        if case["id"] in SPLIT["test"]["cases"]:
            given = case["input"]
            held_out.extend([given] if isinstance(given, str) else given)
    for name in SPLIT["test"]["cases"]:
        document = EVALS / "documents" / f"{name}.md"
        if document.is_file():
            held_out.append(document.read_text(encoding="utf-8"))
    for benchmark in SPLIT["test"]["benchmarks"]:
        for document in sorted((EVALS / "benchmarks" / benchmark).glob("*.md")):
            held_out.append(document.read_text(encoding="utf-8"))
    held = set().union(*(_shingles(t) for t in held_out))
    for example in ALL_EXAMPLES:
        assert not _shingles(example["input"]["sentence"]) & held, example["id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_the_prefix_is_byte_stable_and_the_examples_follow_it(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    session_id = uuid.uuid4()
    fake_llm.answer(recorded("insight_sells_services"), recorded("insight_three_areas"))

    await teach(client, tenant, company_id, FIRST, session_id)
    await teach(client, tenant, company_id, SECOND, session_id)

    first, second = fake_llm.requests
    assert first.system == second.system == SYSTEM_PROMPT
    for request, sentence in ((first, FIRST), (second, SECOND)):
        data = json.loads(request.user)
        # The retrieved examples come before the caller's text.
        assert list(data)[0] == "examples"
        assert data["examples"] == examples_for(sentence, "sentence")
        assert data["examples"]
        assert request.user.index('"examples"') < request.user.index('"sentence"')
        # The reservation's estimate counts the examples; each example's own estimate rounds up
        # once and counts an empty schema, so it may exceed its share by 2 tokens.
        without = json.dumps({k: v for k, v in data.items() if k != "examples"}, ensure_ascii=False)
        bare = LlmRequest(request.system, without, request.output_schema, 0, 0)
        added = sum(example_tokens(e) for e in data["examples"])
        assert estimate_tokens(request) >= estimate_tokens(bare) + added - len(data["examples"]) * 2


def _shingles(text: str, n: int = 6) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.casefold())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}
