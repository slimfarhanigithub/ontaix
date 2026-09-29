"""Pure parts of the teach extraction step: the fallback triggers and the 60-intent cap."""

from __future__ import annotations

import pytest

from app.models.api.teach import Intent
from app.services.teach_draft_service import RULES_NOTE, PlannedIntent, assemble
from app.utilities.teach_triggers import Trigger, fallback_triggers

SECOND = "these services are focused around three areas, app, data and AI"


def test_intents_past_sixty_are_dropped_as_one_unresolved_phrase() -> None:
    def planned(i: int, drafts: int) -> PlannedIntent:
        return PlannedIntent(
            Intent(
                kind="rel",
                subject="a",
                predicate="has",
                object=f"b{i}",
                subject_resolved=None,
                object_resolved=None,
            ),
            [{"type": "concept", "label": f"B{i}"}] * drafts,
            [],
            RULES_NOTE,
            ("a", "has", f"b{i}"),
            span=f"b{i}" if i == 30 else None,
        )

    by_drafts = assemble([planned(i, 2) for i in range(40)], "a has b30")
    assert (len(by_drafts.intents), len(by_drafts.drafts), len(by_drafts.notes)) == (30, 60, 60)
    assert [u.model_dump() for u in by_drafts.unresolved] == [
        {"text": "b30", "reason": "too_many_drafts"}
    ]

    by_intents = assemble([planned(i, 0) for i in range(70)], "a has b")
    assert len(by_intents.intents) == 60 and by_intents.drafts == []
    assert [u.reason for u in by_intents.unresolved] == ["too_many_drafts"]


@pytest.mark.parametrize(
    ("sentence", "outcome", "expected"),
    [
        ("insight sells services", "partly_understood", {"partly", "verb"}),
        (SECOND, "understood", {"back", "list", "verb"}),
        ("a plant has machines", "understood", set()),
        ("a customer places orders", "understood", set()),
        ("a warehouse has loading docks", "understood", set()),
        ("a machine that has run 5,000 hours is a veteran machine", "understood", set()),
        ("they buy from us: steel, glass", "understood", {"back", "verb"}),
        ("these machines feed the plant", "understood", {"back"}),
        ("we have 3 plants: lyon, turin", "understood", {"list"}),
    ],
)
def test_fallback_triggers(sentence: str, outcome: str, expected: set[str]) -> None:
    names = {
        Trigger.PARTLY_UNDERSTOOD: "partly",
        Trigger.NOT_UNDERSTOOD: "not",
        Trigger.BACK_REFERENCE: "back",
        Trigger.LIST_PREAMBLE: "list",
        Trigger.UNKNOWN_VERB: "verb",
    }
    assert {names[t] for t in fallback_triggers(sentence, outcome)} == expected
