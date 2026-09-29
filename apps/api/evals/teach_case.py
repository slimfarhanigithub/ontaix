"""One case of the teach bake-off and the loader of the inline dataset `teach_cases.yaml`.

A case is what a person teaches (typed turns, one spoken recording, or one document) about one
company, the concepts that already exist before it runs, and the concepts and relations a
careful reviewer expects the teach pipeline to draft from it. A case without expectations runs
in report-only mode: what it drafted and what it cost are recorded, nothing is scored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CaseKind = Literal["text", "speech", "document"]
# Where a case comes from: the YAML dataset, the public documents, the public ontology
# benchmarks, or the owner's git-ignored private folder.
CaseOrigin = Literal["dataset", "documents", "benchmarks", "private"]

MAX_TYPED_CHARS = 400
# The longest spoken sentence one `speech` request carries, as the API allows.
MAX_SPOKEN_SENTENCE_CHARS = 4000


def _as_list(value: object) -> object:
    return [value] if isinstance(value, str) else value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ExistingConcept(_Model):
    """A concept seeded (and approved) before the case runs; `parent` is a label or the
    company name. Listed parent first."""

    label: str
    parent: str
    action: str = "has"
    domain: str = "sales"


class ExpectedConcept(_Model):
    """A concept the case should draft. `parent` lists every acceptable parent (an ontology
    class with several superclasses lists them all) and `action` every acceptable verb;
    `aliases` are other labels that name the same concept."""

    label: str
    parent: list[str] = Field(min_length=1)
    action: list[str] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)

    @field_validator("parent", "action", mode="before")
    @classmethod
    def _listed(cls, value: object) -> object:
        return _as_list(value)


class ExpectedRelation(_Model):
    """A relation between two concepts that both exist when it is drafted. `action` is read
    from `source` to `target`; `inverse` lists the actions accepted when the model drafts it
    from `target` to `source`."""

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    action: list[str] = Field(min_length=1)
    inverse: list[str] = Field(default_factory=list)

    @field_validator("action", "inverse", mode="before")
    @classmethod
    def _listed(cls, value: object) -> object:
        return _as_list(value)


class Expected(_Model):
    concepts: list[ExpectedConcept] = Field(default_factory=list)
    relations: list[ExpectedRelation] = Field(default_factory=list)


class TeachCase(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    kind: CaseKind
    origin: CaseOrigin = "dataset"
    company: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    existing: list[ExistingConcept] = Field(default_factory=list)
    # Typed text: one string per turn. Speech: one string per finished spoken sentence of the
    # recording, in the order spoken. Document: either one inline text uploaded as a text
    # file, or `document`, a file on disk.
    input: list[str] = Field(default_factory=list)
    document: Path | None = None
    expected: Expected | None = None
    # Labels that are neither invented nor missed when drafted (reasonable either way).
    optional: list[str] = Field(default_factory=list)
    # What the expectation's source left out (for an ontology: axioms and datatypes).
    source_report: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input", mode="before")
    @classmethod
    def _listed(cls, value: object) -> object:
        return _as_list(value)

    @model_validator(mode="after")
    def _input_fits_the_channel(self) -> TeachCase:
        if self.document is not None:
            if self.kind != "document" or self.input:
                raise ValueError(f"{self.id}: a document file replaces the input")
            return self
        if not self.input or any(not turn.strip() for turn in self.input):
            raise ValueError(f"{self.id}: input is empty")
        if self.kind == "text" and any(len(t) > MAX_TYPED_CHARS for t in self.input):
            raise ValueError(f"{self.id}: a typed turn holds at most {MAX_TYPED_CHARS} characters")
        if self.kind == "document" and len(self.input) != 1:
            raise ValueError(f"{self.id}: an inline document case has one input")
        if self.kind == "speech" and any(len(s) > MAX_SPOKEN_SENTENCE_CHARS for s in self.input):
            raise ValueError(
                f"{self.id}: a spoken sentence holds at most {MAX_SPOKEN_SENTENCE_CHARS} chars"
            )
        return self

    @property
    def scored(self) -> bool:
        return self.expected is not None


def load_cases(path: Path) -> list[TeachCase]:
    """Every case of the inline dataset, in file order; each must carry expectations."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = [TeachCase.model_validate(item) for item in raw["cases"]]
    unscored = [c.id for c in cases if c.expected is None]
    if unscored:
        raise ValueError(f"dataset cases without expectations: {', '.join(unscored)}")
    ensure_unique(cases)
    return cases


def ensure_unique(cases: list[TeachCase]) -> None:
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate case ids: {', '.join(duplicates)}")
