"""Recorded model answers against the teach extraction contract, and a live provider check.

The live test calls the configured provider and runs only when ONTAIX_FOUNDRY_ENDPOINT is set
(with `az login` and a price for ONTAIX_LLM_MODEL in ONTAIX_LLM_PRICE_TABLE); CI never sets it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema
import pytest

from app.ai.prompts.teach_extraction import MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.clients.llm_client import LlmRequest, get_llm_client
from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from tests.llm_fakes import recorded

# ONTAIX_CONTRACTS_DIR points at another copy of the contracts, for example a branch's.
CONTRACTS = Path(
    os.environ.get("ONTAIX_CONTRACTS_DIR") or Path(__file__).resolve().parents[3] / "contracts"
)
CONTRACT = CONTRACTS / "teach-extraction.schema.json"
VALID = (
    "insight_sells_services",
    "insight_three_areas",
    "injection_unknown_handle",
    "speech_insight_transcript",
    "services_offerings",
    "services_offerings_count_mismatch",
    "speech_services_offerings",
)


def contract() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(json.loads(CONTRACT.read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", VALID)
def test_recorded_answers_follow_the_contract_and_the_provider_format(name: str) -> None:
    answer = json.loads(recorded(name))
    contract().validate(answer)
    jsonschema.Draft202012Validator(OUTPUT_SCHEMA).validate(answer)
    TeachExtractionAnswer.model_validate_json(recorded(name))


@pytest.mark.parametrize("name", ["injection_markup_label", "injection_format_character"])
def test_answers_with_refused_characters_fail_the_api_validation(name: str) -> None:
    with pytest.raises(ValueError):
        TeachExtractionAnswer.model_validate_json(recorded(name))


def test_the_contract_refuses_markup_the_api_refuses() -> None:
    assert not contract().is_valid(json.loads(recorded("injection_markup_label")))


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("ONTAIX_FOUNDRY_ENDPOINT"), reason="ONTAIX_FOUNDRY_ENDPOINT is not set"
)
@pytest.mark.asyncio(loop_scope="session")
async def test_the_configured_provider_answers_the_first_sentence() -> None:
    client = get_llm_client()
    assert client is not None
    data = {
        "sentence": "Insight sells services",
        "domainPrefix": None,
        "company": "Insight",
        "sessionTurns": [],
        "candidates": [
            {"handle": "c0", "label": "Insight", "domain": None, "parent": None, "pending": False}
        ],
        "domainTemplates": [{"key": "sales", "name": "Sales"}],
    }
    answer = await client.complete(
        LlmRequest(SYSTEM_PROMPT, json.dumps(data), OUTPUT_SCHEMA, MAX_OUTPUT_TOKENS, 15.0)
    )
    parsed = TeachExtractionAnswer.model_validate_json(answer.text)
    contract().validate(json.loads(answer.text))
    assert any(i.kind == "rel" for i in parsed.intents)
