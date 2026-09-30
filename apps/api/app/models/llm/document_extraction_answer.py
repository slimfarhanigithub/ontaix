"""The only answers the model steps of a whole-document extraction job may return: an outline
answer (pass 1) or a section answer (pass 2), no extra keys, and free text that refuses markup,
controls, U+00A0, line separators and every Unicode format character.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.models.llm.teach_extraction_answer import DomainKey, FreeText
from app.utilities.action_text import has_refused_character

HANDLE_PATTERN = r"^(c(0|[1-9][0-9]?|1[0-9]{2})|o[1-9][0-9]{0,4})$"
KEY_PATTERN = r"^k[1-9][0-9]{0,3}$"

Role = Literal["domain_area", "process", "subprocess", "step", "entity", "group"]


def _no_refused(value: str) -> str:
    if has_refused_character(value):
        raise ValueError("refused character")
    return value


def _trimmed(value: str) -> str:
    if value[:1].isspace() or value[-1:].isspace():
        raise ValueError("surrounding space")
    return value


def _lower_ascii(value: str) -> str:
    if any("A" <= c <= "Z" for c in value):
        raise ValueError("upper-case letter")
    return value


Label = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(_no_refused), AfterValidator(_trimmed)
]
Action = Annotated[
    str,
    Field(min_length=1, max_length=60),
    AfterValidator(_no_refused),
    AfterValidator(_trimmed),
    AfterValidator(_lower_ascii),
]
Quote = Annotated[FreeText, Field(min_length=1, max_length=400)]
Confidence = Annotated[float, Field(ge=0, le=1)]
SentenceIndex = Annotated[int, Field(ge=0, le=1999)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class HandleRef(_Strict):
    handle: str = Field(pattern=HANDLE_PATTERN)


class KeyRef(_Strict):
    key: str = Field(pattern=KEY_PATTERN)


class PathRef(_Strict):
    path: list[Label] = Field(min_length=1)


class NewLabelRef(_Strict):
    new_label: Label = Field(alias="newLabel")


Ref = HandleRef | KeyRef | PathRef
IntentRef = HandleRef | KeyRef | PathRef | NewLabelRef


class OutlineNode(_Strict):
    key: str = Field(pattern=KEY_PATTERN)
    parent: Ref
    label: Label
    action: Action
    role: Role
    domain_key: DomainKey | None = Field(default=None, alias="domainKey")
    confidence: Confidence
    sentence_index: SentenceIndex = Field(alias="sentenceIndex")
    span: Quote


class OutlineAnswer(_Strict):
    pass_: Literal["outline"] = Field(alias="pass")
    nodes: list[OutlineNode] = Field(max_length=400)


class SectionIntent(_Strict):
    kind: Literal["rel", "spec"]
    subject: IntentRef
    object: IntentRef
    action: Action | None = None
    rule: Annotated[FreeText, Field(max_length=200)] | None = None
    domain_key: DomainKey | None = Field(default=None, alias="domainKey")
    confidence: Confidence
    explanation: Annotated[FreeText, Field(max_length=120)] | None = None
    sentence_index: SentenceIndex = Field(alias="sentenceIndex")
    span: Quote

    @model_validator(mode="after")
    def _kind_fields(self) -> SectionIntent:
        if self.kind == "spec" and self.rule is not None and self.action is not None:
            raise ValueError("a spec intent with a rule has no action")
        return self


class ModelUnresolved(_Strict):
    sentence_index: SentenceIndex = Field(alias="sentenceIndex")
    reason: Literal["not_understood", "ambiguous_reference", "not_a_statement"]


class SectionAnswer(_Strict):
    pass_: Literal["section"] = Field(alias="pass")
    intents: list[SectionIntent] = Field(max_length=400)
    unresolved: list[ModelUnresolved] = Field(max_length=100)
