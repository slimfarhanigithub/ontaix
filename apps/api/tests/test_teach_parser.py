"""The teach grammar reads a sentence exactly as the Studio's parser does."""

from __future__ import annotations

from app.utilities.teach_parser import (
    ParsedIntent,
    clean_np,
    content_words,
    domain_prefix,
    singular,
    split_list,
    understand,
)


def test_parser_reads_like_the_studio() -> None:
    assert [singular(w) for w in ("machines", "inspections", "deliveries", "batches")] == [
        "machine",
        "inspection",
        "delivery",
        "batch",
    ]
    assert clean_np("every production line,") == "production line"
    assert clean_np("the new sensors") == "sensor"
    assert understand("A line has machines and sensors.") == [
        ParsedIntent("rel", subj="line", pred="has", obj="machine"),
        ParsedIntent("rel", subj="line", pred="has", obj="sensor"),
    ]
    assert understand("Materials are bought from suppliers") == [
        ParsedIntent("rel", subj="material", pred="is bought from", obj="supplier")
    ]
    assert understand("A plant ships products to customers") == [
        ParsedIntent("rel", subj="plant", pred="ships to", obj="customer"),
        ParsedIntent("rel", subj="plant", pred="ships", obj="product"),
    ]
    assert understand("Operators are employees") == [
        ParsedIntent("spec", subj="operator", obj="employee")
    ]
    assert understand("A machine that has run 5,000 hours is a machine due for maintenance") == [
        ParsedIntent(
            "spec", subj="machine due for maintenance", rule="has run 5,000 hours", obj="machine"
        )
    ]
    assert domain_prefix("In quality, a defect is raised") == ("quality", "a defect is raised")
    assert domain_prefix("In HR, people train")[0] == "people"
    assert domain_prefix("Plants run lines")[0] is None
    assert content_words("The plants have many downtimes!") == ["plant", "downtime"]
    assert split_list("a, b and c") == ["a", "b", "c"]
