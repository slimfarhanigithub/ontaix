"""Proposal drafts as lessons hold them: compact, label-only structures, and how they compare.

A lesson never holds an id: every concept a draft names is written as its label, so a lesson
reads the same to a model long after the ids it was built from are gone. The functions are pure;
the caller passes the label of each id it knows.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any

# The draft keys that never change what a draft states: its layout seed, its panel caption and
# its provenance. Two drafts equal on every other key state the same fact.
PRESENTATION_KEYS = frozenset({"seed", "caption", "origin", "importRef"})

_WORD = re.compile(r"\w+")

LabelOf = Callable[[str], str | None]


def compact(draft: dict[str, Any], label_of: LabelOf) -> dict[str, Any] | None:
    """A draft as a lesson shows it: its type and the labels, action, domain and values it
    states, ids replaced by labels. None for a draft of any other type, or one naming an id
    `label_of` does not know."""
    kind = draft.get("type")

    def named(id_key: str, label_key: str) -> str | None:
        if draft.get(id_key):
            return label_of(str(draft[id_key]))
        label = draft.get(label_key)
        return str(label) if label else None

    if kind in ("concept", "spec"):
        parent = named("parentId", "parentLabel")
        if parent is None:
            return None
        out: dict[str, Any] = {"type": kind, "label": draft["label"], "parent": parent}
        if kind == "concept":
            out["action"] = draft.get("action") or "relates to"
            if draft.get("reverse"):
                out["reverse"] = True
        elif draft.get("rule"):
            out["rule"] = draft["rule"]
        if draft.get("domainKey"):
            out["domain"] = draft["domainKey"]
        return out
    if kind == "relation":
        a, b = named("aId", "aLabel"), named("bId", "bLabel")
        if a is None or b is None:
            return None
        return {"type": "relation", "a": a, "action": draft["action"], "b": b}
    if kind == "attr":
        concept = named("conceptId", "conceptLabel")
        if concept is None or draft.get("value") is None:
            return None
        return {
            "type": "attr",
            "concept": concept,
            "name": draft["name"],
            "attributeType": draft.get("attributeType"),
            "value": draft["value"],
        }
    return None


def structure(drafts: Iterable[dict[str, Any] | None]) -> dict[str, Any]:
    """The lesson structure of compact drafts, in order, each once."""
    kept: list[dict[str, Any]] = []
    for d in drafts:
        if d is not None and d not in kept:
            kept.append(d)
    return {"drafts": kept}


def merged(*structures: dict[str, Any] | None) -> dict[str, Any]:
    """One structure holding the drafts of every given structure, in order, each once."""
    return structure(d for s in structures if s for d in s.get("drafts", []))


def labels(struct: dict[str, Any] | None) -> list[str]:
    """Every label a structure names, in order, each once."""
    out: list[str] = []
    for d in (struct or {}).get("drafts", []):
        for key in ("label", "parent", "a", "b", "concept"):
            value = d.get(key)
            if isinstance(value, str) and value not in out:
                out.append(value)
    return out


def new_labels(struct: dict[str, Any] | None) -> list[str]:
    """The labels of the concepts a structure introduces, in order, each once."""
    out: list[str] = []
    for d in (struct or {}).get("drafts", []):
        if d.get("type") in ("concept", "spec") and d["label"] not in out:
            out.append(d["label"])
    return out


def touched(struct: dict[str, Any] | None, ignore: Iterable[str] = ()) -> set[str]:
    """The folded labels a structure touches, without the `ignore` labels (the company root):
    two structures touching one label speak about the same subject."""
    ignored = {fold(label) for label in ignore}
    return {fold(label) for label in labels(struct)} - ignored


def fold(label: str) -> str:
    """A label compared without case, width or repeated whitespace."""
    return " ".join(unicodedata.normalize("NFKC", label).casefold().split())


def draft_key(draft: dict[str, Any]) -> str:
    """A draft's statement as one comparable string: every key but the presentation keys,
    unset values dropped, keys sorted."""
    kept = {
        k: v for k, v in draft.items() if k not in PRESENTATION_KEYS and v is not None and v != ""
    }
    return json.dumps(kept, sort_keys=True, ensure_ascii=False)


def ranked_text(source_text: str, struct: dict[str, Any] | None) -> str:
    """What the lesson ranking compares: the source text and every label of the structure."""
    return " ".join([source_text, *labels(struct)])


def words_occur(phrase: str, text: str) -> bool:
    """True when the words of `phrase` occur in `text` as whole words, in order and adjacent,
    ignoring case and the characters between words."""
    wanted = _WORD.findall(fold(phrase))
    if not wanted:
        return False
    have = _WORD.findall(fold(text))
    n = len(wanted)
    return any(have[i : i + n] == wanted for i in range(len(have) - n + 1))
