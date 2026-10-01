"""Source ranges recovered from drifting offsets and from quotes in another Unicode form.

The model's offsets drift by a few code points along accented text and its quotes come back
in another normalisation form or with typographic apostrophes; grounding still finds the
words the model meant. Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import json
import unicodedata

import httpx
import pytest

from app.services.teach_extraction_service import _occurrences_folded
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import births, speak

FRENCH = (
    "bon alors euh l'hôpital a un service des urgences et les urgences euh font d'abord le tri "
    "non attends d'abord l'accueil et ensuite le tri et le tri attribue un niveau de priorité"
)


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def typographic(text: str) -> str:
    return text.replace("'", "’")


def rel(
    subject: dict, obj: dict, action: str, source: tuple[int, int], span: str | None = None
) -> dict:
    intent = {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.9,
        "segment": 0,
        "source": {"start": source[0], "end": source[1]},
    }
    if span is not None:
        intent["span"] = span
    return intent


def new(label: str) -> dict:
    return {"newLabel": label}


@pytest.mark.asyncio(loop_scope="session")
async def test_accented_quotes_and_offsets_inside_words_still_ground_the_labels(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Centre hospitalier de Morvelle")
    await configure(tenant)
    urgences = FRENCH.index("l'hôpital a un service des urgences")
    accueil = FRENCH.index("urgences euh font")
    ensuite = FRENCH.index("ensuite")
    tri = FRENCH.index("le tri attribue")
    fake_llm.answer(
        json.dumps(
            {
                "segments": [{"index": 0, "start": 0, "end": len(FRENCH)}],
                "intents": [
                    rel(
                        {"candidate": "c0"},
                        new("Service des urgences"),
                        "a",
                        (urgences, urgences + 35),
                        "l'hôpital a un service des urgences",
                    ),
                    # No quote; the offsets start inside "urgences" and end inside "ensuite".
                    rel(
                        new("Service des urgences"),
                        new("Accueil"),
                        "font",
                        (accueil + 2, ensuite + 2),
                    ),
                    # A decomposed quote with a typographic apostrophe, offsets drifted.
                    rel(
                        new("Service des urgences"),
                        new("Tri"),
                        "font",
                        (accueil + 3, accueil + 40),
                        nfd(typographic("les urgences euh font d'abord le tri")),
                    ),
                    rel(
                        new("Tri"),
                        new("Niveau de priorité"),
                        "attribue",
                        (tri + 3, len(FRENCH)),
                        nfd("le tri attribue un niveau de priorité"),
                    ),
                ],
                "unresolved": [],
            },
            ensure_ascii=False,
        )
    )

    result = await speak(client, tenant, company_id, FRENCH)

    assert result["unresolved"] == []
    assert births(result) == [
        ("Service des urgences", str(root_id), "a"),
        ("Accueil", "Service des urgences", "font"),
        ("Tri", "Service des urgences", "font"),
        ("Niveau de priorité", "Tri", "attribue"),
    ]
    spans = [n["sourceSpan"] for n in result["draftNotes"]]
    # The second intent's range is widened to the edges of the words its offsets cut.
    assert spans[1] == {"start": accueil, "end": ensuite + len("ensuite")}
    assert spans[3] == {"start": tri, "end": len(FRENCH)}


def test_a_loose_match_ignores_accents_and_the_shape_of_apostrophes() -> None:
    text = "le tri attribue un niveau de priorité"

    assert _occurrences_folded(text, nfd("niveau de PRIORITÉ")) == []
    assert _occurrences_folded(text, nfd("niveau de PRIORITÉ"), loose=True) == [(19, 37)]
    assert _occurrences_folded(nfd(text), "priorité", loose=True) == [(29, 38)]
    assert _occurrences_folded("l'accueil", typographic("l'accueil"), loose=True) == [(0, 9)]
    assert _occurrences_folded("l'accueil", typographic("l'accueil")) == []
