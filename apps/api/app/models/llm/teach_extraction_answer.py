"""The only answer the teach extraction model step may return: at most 20 intents and 10
unresolved phrases, no extra keys, and free text that refuses markup, controls, U+00A0, line
separators and every Unicode format character.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.utilities.action_text import has_refused_character

DomainKey = Literal[
    "production",
    "supply",
    "sales",
    "logistics",
    "quality",
    "maintenance",
    "finance",
    "people",
    "engineering",
]

_UPPER_ASCII = re.compile("[A-Z]")


def _free_text(value: str) -> str:
    if has_refused_character(value):
        raise ValueError("refused character")
    return value


def _trimmed(value: str) -> str:
    if value[:1].isspace() or value[-1:].isspace():
        raise ValueError("surrounding space")
    return value


def _lower_ascii(value: str) -> str:
    if _UPPER_ASCII.search(value):
        raise ValueError("upper-case letter")
    return value


FreeText = Annotated[str, AfterValidator(_free_text)]
Label = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(_free_text), AfterValidator(_trimmed)
]
Action = Annotated[
    str,
    Field(min_length=1, max_length=60),
    AfterValidator(_free_text),
    AfterValidator(_trimmed),
    AfterValidator(_lower_ascii),
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CandidateRef(_Strict):
    candidate: str = Field(pattern=r"^c(0|[1-9][0-9]?|1[0-9]{2})$")


class NewLabelRef(_Strict):
    new_label: Label = Field(alias="newLabel")


ConceptRef = CandidateRef | NewLabelRef


Index = Annotated[int, Field(ge=0, le=39)]


class Span(_Strict):
    """A half-open range [start, end) of Unicode code points in the text the API sent."""

    start: int = Field(ge=0, le=3999)
    end: int = Field(ge=1, le=4000)

    @model_validator(mode="after")
    def _ordered(self) -> Span:
        if self.start >= self.end:
            raise ValueError("a range needs start < end")
        return self


class Segment(_Strict):
    index: Index
    start: int = Field(ge=0, le=3999)
    end: int = Field(ge=1, le=4000)

    @model_validator(mode="after")
    def _ordered(self) -> Segment:
        if self.start >= self.end:
            raise ValueError("a range needs start < end")
        return self


class AnswerIntent(_Strict):
    kind: Literal["rel", "spec"]
    subject: ConceptRef
    object: ConceptRef
    action: Action | None = None
    rule: Annotated[FreeText, Field(max_length=200)] | None = None
    domain_key: DomainKey | None = Field(default=None, alias="domainKey")
    confidence: float = Field(ge=0, le=1)
    explanation: Annotated[FreeText, Field(max_length=300)] | None = None
    span: Annotated[FreeText, Field(max_length=400)] | None = None
    segment: Index | None = None
    source: Span
    members: list[ConceptRef] | None = Field(default=None, min_length=1, max_length=20)
    member_action: Action | None = Field(default=None, alias="memberAction")
    stated_count: int | None = Field(default=None, ge=0, le=1000, alias="statedCount")
    list_id: Index | None = Field(default=None, alias="listId")

    @model_validator(mode="after")
    def _kind_fields(self) -> AnswerIntent:
        if self.kind == "rel" and (self.action is None or self.rule is not None):
            raise ValueError("a rel intent has an action and no rule")
        if self.kind == "spec" and self.action is not None:
            raise ValueError("a spec intent has no action")
        if self.kind == "spec" and (
            self.members is not None or self.member_action is not None or self.list_id is not None
        ):
            raise ValueError("a spec intent has no members, memberAction or listId")
        if self.members is None and self.member_action is not None:
            raise ValueError("memberAction needs members")
        if self.stated_count is not None and self.members is None and self.list_id is None:
            raise ValueError("statedCount needs members or listId")
        return self


class AnswerUnresolved(_Strict):
    text: Annotated[FreeText, Field(min_length=1, max_length=400)]
    reason: Literal["not_understood", "ambiguous_reference", "low_confidence", "not_a_statement"]
    segment: Index | None = None
    source: Span | None = None


class TeachExtractionAnswer(_Strict):
    """The schema's caps are those of a speech transcript; the API applies the smaller caps of a
    typed or document sentence (20 intents, 10 phrases) after parsing."""

    intents: list[AnswerIntent] = Field(max_length=60)
    unresolved: list[AnswerUnresolved] = Field(max_length=30)
    segments: list[Segment] | None = Field(default=None, max_length=40)
