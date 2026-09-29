"""The bake-off scorer, aggregation, composite and stage helpers: pure functions, no database."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.aggregate import CaseUsage, summarise
from evals.candidate import UnpricedCandidate, at_effort, load_candidates, run_configs
from evals.composite import composites, mean_std, paired, sign_test
from evals.scoring import (
    PredictedConcept,
    PredictedRelation,
    action_matches,
    drafted_depth,
    grounded,
    normalise_action,
    normalise_label,
    score_case,
)
from evals.stages import stratified_subset
from evals.teach_case import TeachCase

EVALS = Path(__file__).parent.parent / "evals"

GROUPING = TeachCase.model_validate(
    {
        "id": "grouping",
        "kind": "text",
        "company": "Insight",
        "input": ["Insight sells services.", "Services has 3 offerings, apps, data and AI."],
        "expected": {
            "concepts": [
                {"label": "Services", "parent": "Insight", "action": "sells"},
                {"label": "Offerings", "parent": "Services", "action": "has"},
                {"label": "Apps", "parent": "Offerings", "action": "includes"},
                {"label": "Data", "parent": "Offerings", "action": "includes"},
                {"label": "AI", "parent": "Offerings", "action": "includes"},
            ]
        },
    }
)
SOURCE = " ".join(GROUPING.input)


def c(label: str, parent: str, action: str, reverse: bool = False) -> PredictedConcept:
    return PredictedConcept(label, parent, action, reverse)


def perfect() -> list[PredictedConcept]:
    return [
        c("Services", "Insight", "sells"),
        c("Offerings", "Services", "has"),
        c("Apps", "Offerings", "includes"),
        c("Data", "Offerings", "includes"),
        c("AI", "Offerings", "includes"),
    ]


def test_labels_normalise_case_plural_articles_and_punctuation() -> None:
    assert normalise_label("The Apps") == normalise_label("app")
    assert normalise_label("Order-to-Cash") == "order to cash"
    assert normalise_label("R&D") == normalise_label("r and d")
    assert normalise_label("AI") == "ai"


def test_actions_normalise_and_match_through_synonyms() -> None:
    assert normalise_action("are focused on") == normalise_action("is focused on")
    assert normalise_action("Focuses on") == "focus on"
    assert action_matches("includes", ["has"])
    assert action_matches("is split into", ["contains"])
    assert action_matches("offers", ["sells"])
    assert not action_matches("sells", ["has"])


def test_grounding_is_whole_word_and_normalised() -> None:
    assert grounded("Apps", "we build app and data platforms")
    assert grounded("Data Platforms", "we build app and data platform")
    assert not grounded("Data Platforms", "we build dataplatforms")
    assert not grounded("Cash", "cashflow matters")


def test_a_perfect_draft_scores_one_everywhere() -> None:
    s = score_case(GROUPING, perfect(), [], SOURCE)

    assert (s.concept_precision, s.concept_recall, s.concept_f1) == (1.0, 1.0, 1.0)
    assert s.parent_correct == s.action_correct == s.path_correct == 5
    assert s.invented == [] and s.missed == [] and s.missing_branches == []
    assert (s.depth_expected, s.depth_achieved) == (3, 3)
    assert s.grounding_ceiling == 1.0
    assert {lv: (v.expected, v.predicted, v.correct) for lv, v in s.levels.items()} == {
        1: (1, 1, 1),
        2: (1, 1, 1),
        3: (3, 3, 3),
    }


def test_the_descriptive_reading_invents_nothing_but_misses_the_group() -> None:
    drafts = [
        c("Services", "Insight", "sells"),
        c("Apps", "Services", "focuses on"),
        c("Data", "Services", "focuses on"),
        c("AI", "Services", "focuses on"),
    ]

    s = score_case(GROUPING, drafts, [], SOURCE)

    assert s.missed == ["Offerings"]
    assert s.missing_branches == ["Offerings (1 nodes)"]
    assert s.concept_precision == 1.0 and s.concept_recall == 0.8
    assert s.parent_correct == 1 and len(s.wrong_parent) == 3
    assert s.action_correct == 1 and len(s.wrong_action) == 3
    assert s.path_correct == 1
    assert s.depth_achieved == 2


def test_invented_and_duplicated_concepts_lower_precision() -> None:
    case = TeachCase.model_validate(
        {
            **GROUPING.model_dump(by_alias=True),
            "existing": [{"label": "Services", "parent": "Insight", "action": "sells"}],
            "optional": ["Areas"],
        }
    )
    drafts = [*perfect(), c("Areas", "Services", "has"), c("Cloud", "Services", "has")]

    s = score_case(case, drafts, [], SOURCE)

    assert s.optional_drafted == ["Areas"]
    assert s.invented == ["Cloud"]
    assert s.duplicates == []
    again = score_case(case, [*perfect(), c("App", "Offerings", "includes")], [], SOURCE)
    assert again.duplicates == ["App"] and again.invented == ["App"]


def test_a_wrong_intermediate_breaks_the_path_of_everything_below() -> None:
    drafts = [
        c("Services", "Insight", "sells"),
        c("Offerings", "Catalogue", "has"),
        c("Apps", "Offerings", "includes"),
    ]

    s = score_case(GROUPING, drafts, [], SOURCE)

    assert s.parent_correct == 2
    assert s.path_correct == 1
    assert any(w.startswith("Apps: got") for w in s.wrong_path)


def test_multiple_parents_accept_either_and_levels_have_no_depth_limit() -> None:
    chain = [
        {"label": f"L{i}", "parent": "Acme" if i == 1 else f"L{i - 1}", "action": "has"}
        for i in range(1, 9)
    ]
    chain[4]["parent"] = ["L4", "L2"]
    case = TeachCase.model_validate(
        {
            "id": "deep",
            "kind": "text",
            "company": "Acme",
            "input": ["x"],
            "expected": {"concepts": chain},
        }
    )
    drafts = [
        c(n["label"], n["parent"] if isinstance(n["parent"], str) else "L2", "has") for n in chain
    ]

    s = score_case(case, drafts, [], "")

    assert s.path_correct == 8 and s.parent_correct == 8
    # L5 may hang under L2, so everything from L5 down sits one level higher (shortest path).
    assert max(s.levels) == 6
    assert s.depth_expected == 6
    assert s.grounding_ceiling == 0.0 and s.concept_recall_groundable == 1.0


def test_relations_match_either_direction_and_through_concepts() -> None:
    case = TeachCase.model_validate(
        {
            "id": "rel",
            "kind": "text",
            "company": "Kestrel",
            "input": ["Each order is billed by an invoice. Machines need a plan."],
            "existing": [
                {"label": "Order", "parent": "Kestrel"},
                {"label": "Invoice", "parent": "Kestrel"},
                {"label": "Machine", "parent": "Kestrel"},
            ],
            "expected": {
                "relations": [
                    {
                        "from": "Order",
                        "to": "Invoice",
                        "action": "is billed by",
                        "inverse": "bills",
                    },
                    {"from": "Machine", "to": "Maintenance Plan", "action": "needs"},
                ]
            },
        }
    )

    s = score_case(
        case,
        [c("Maintenance Plan", "Machine", "needs")],
        [PredictedRelation("Invoice", "Order", "bills")],
        "",
    )

    assert s.relations_matched == 2 and s.relation_action_correct == 2
    assert s.invented == [] and s.invented_relations == []


def test_report_only_depth_follows_the_drafts() -> None:
    case = GROUPING.model_copy(update={"expected": None})
    assert drafted_depth(case, perfect()) == 3
    with pytest.raises(ValueError):
        score_case(case, perfect(), [], SOURCE)


def test_summaries_levels_and_composite_rank_precision_first() -> None:
    good = score_case(GROUPING, perfect(), [], SOURCE)
    noisy = score_case(GROUPING, [*perfect(), c("Cloud", "Services", "has")], [], SOURCE)
    usage = CaseUsage(calls=2, cost_eur=0.01, latencies_ms=[1000, 3000])
    a = summarise("a@none", "all", [(good, usage)])
    b = summarise("b@none", "all", [(noisy, usage)])

    assert a.levels[3].f1 == 1.0 and b.concept_precision == pytest.approx(5 / 6)
    assert a.p95_latency_s == 3.0
    ranked = composites([a, b])
    assert ranked["a@none"].total > ranked["b@none"].total


def test_an_unpriced_model_is_not_the_cheapest() -> None:
    s = score_case(GROUPING, perfect(), [], SOURCE)
    priced = summarise("p", "all", [(s, CaseUsage(calls=1, cost_eur=0.02, latencies_ms=[10]))])
    unpriced = summarise("u", "all", [(s, CaseUsage(calls=1, cost_eur=0.0, latencies_ms=[10]))])

    result = composites([priced, unpriced])

    assert result["p"].efficiency == 1.0 and result["u"].efficiency == 0.75


def test_statistics_mean_std_sign_test_and_pairing() -> None:
    assert mean_std([1.0, 2.0, 3.0]) == (2.0, 1.0)
    assert mean_std([4.0]) == (4.0, 0.0)
    assert sign_test(0, 0) == 1.0
    assert sign_test(8, 0) == pytest.approx(2 / 256)
    p = paired("x", "base", {"a": 0.9, "b": 0.8, "c": 0.5}, {"a": 0.8, "b": 0.8, "c": 0.6})
    assert (p.wins, p.ties, p.losses, p.cases) == (1, 1, 1, 3)
    assert p.mean_diff == pytest.approx(0.0)


def test_the_stratified_subset_is_stable_and_covers_every_stratum() -> None:
    cases = [
        TeachCase.model_validate(
            {"id": f"{kind}-{i}", "kind": kind, "company": "X", "input": ["hello there"]}
        )
        for kind in ("text", "speech")
        for i in range(10)
    ]

    first = stratified_subset(cases, 0.3, "seed")

    assert first == stratified_subset(cases, 0.3, "seed")
    assert sum(1 for c in first if c.kind == "text") == 3
    assert sum(1 for c in first if c.kind == "speech") == 3


def test_candidates_are_the_deployed_models_with_residency_and_accepted_efforts() -> None:
    file = load_candidates(EVALS / "candidates.yaml")
    assert {c.deployment for c in file.candidates} == {
        "gpt-6-sol",
        "claude-sonnet-5",
        "claude-sonnet-5-5",
        "claude-fable-5-1",
    }
    configs = run_configs(file, None, ["none"])
    keys = {c.key for c in configs}

    assert keys == {"gpt-6-sol@none", "claude-sonnet-5@none"}
    by_deployment = {c.deployment: c for c in run_configs(file, None, None)}
    assert by_deployment["gpt-6-sol"].residency == "eu_data_zone"
    assert by_deployment["gpt-6-sol"].provider == "azure_foundry"
    assert by_deployment["gpt-6-sol"].endpoint is None
    for claude in ("claude-sonnet-5", "claude-sonnet-5-5", "claude-fable-5-1"):
        assert by_deployment[claude].residency == "global"
        assert by_deployment[claude].provider == "anthropic_foundry"
        assert by_deployment[claude].endpoint == (
            "https://ais-ontaix-dev-sdc-02a13.cognitiveservices.azure.com/"
        )
    with pytest.raises(ValueError):
        run_configs(file, ["no-such-model"], None)


def test_the_smart_plan_takes_the_closest_effort_each_model_accepts() -> None:
    file = load_candidates(EVALS / "candidates.yaml")
    by_name = {c.deployment: c for c in file.candidates}

    assert at_effort(by_name["gpt-6-sol"], "medium").key == "gpt-6-sol@medium"
    assert at_effort(by_name["claude-sonnet-5"], "none").key == "claude-sonnet-5@none"
    assert at_effort(by_name["claude-sonnet-5-5"], "none").key == "claude-sonnet-5-5@low"
    assert at_effort(by_name["claude-fable-5-1"], "none").key == "claude-fable-5-1@low"
    assert at_effort(by_name["claude-fable-5-1"], "high").key == "claude-fable-5-1@high"


def test_a_candidate_without_a_price_is_refused(tmp_path: Path) -> None:
    text = (EVALS / "candidates.yaml").read_text(encoding="utf-8")
    unpriced = tmp_path / "candidates.yaml"
    unpriced.write_text(
        text.replace("price: {inputEurPerMTok: 8.6, outputEurPerMTok: 43.0}", "price: null"),
        encoding="utf-8",
    )

    with pytest.raises(UnpricedCandidate, match="claude-fable-5-1"):
        load_candidates(unpriced)
