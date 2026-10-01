"""The bake-off's whole-document mode: one extraction job per document, run in process.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import json

import httpx
import pytest

from evals.input_modes import DocumentCache, WholeDocumentMode
from evals.teach_case import TeachCase
from evals.workspace import Workspace
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_document_extraction import DOCUMENT, OUTLINE, SECTIONS

CASE = TeachCase.model_validate(
    {
        "id": "plant",
        "kind": "document",
        "company": "Our company",
        "input": [DOCUMENT],
        "expected": {
            "concepts": [
                {"label": "Paint shop", "parent": "Our company", "action": "runs"},
                {"label": "Spray booth", "parent": "Paint shop", "action": "includes"},
                {"label": "Drying oven", "parent": "Paint shop", "action": "includes"},
                {"label": "Robots", "parent": "Spray booth", "action": "uses"},
            ]
        },
    }
)


@pytest.mark.asyncio(loop_scope="session")
async def test_whole_mode_runs_the_job_in_process_and_proposes_its_drafts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    fake_llm.answer(OUTLINE, SECTIONS)
    ws = Workspace(client, CASE)
    await ws.open()

    output = await WholeDocumentMode().run(ws, CASE, DocumentCache())

    [unit] = output.units
    assert (unit.status, unit.extractor, unit.llm_outcome, unit.outcome) == (
        200,
        "llm",
        "used",
        "understood",
    )
    assert [d["label"] for d in unit.drafts] == [
        "Paint shop",
        "Spray booth",
        "Drying oven",
        "Robots",
        "Quality inspectors",
        "Coating",
    ]
    assert unit.submitted == 6 and unit.submit_error is None
    assert len(unit.unresolved) == 4
    assert output.document is not None
    assert output.document["sentences"] == 4
    assert output.document["job"]["chunks"] == 1
    assert output.document["job"]["outlineNodes"] == 3
    assert output.document["job"]["failureReason"] is None
    assert [json.loads(r.user)["pass"] for r in fake_llm.requests] == ["outline", "section"]
