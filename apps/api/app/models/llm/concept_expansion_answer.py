"""The only answer the concept expansion model step may return: suggestions under the handle
`e0` at any depth and links between them, no extra keys, and free text that refuses markup,
controls, U+00A0, line separators and every Unicode format character.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.llm.teach_extraction_answer import DomainKey, FreeText
from app.utilities.action_text import has_refused_character

MAX_ITEMS = 2000
KEY_PATTERN = r"^s[1-9][0-9]{0,3}$"
REF_PATTERN = r"^(e0|s[1-9][0-9]{0,3})$"


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
    str, Field(min_length=1, max_length=60), AfterValidator(_no_refused), AfterValidator(_trimmed)
]
Action = Annotated[
    str,
    Field(min_length=1, max_length=60),
    AfterValidator(_no_refused),
    AfterValidator(_trimmed),
    AfterValidator(_lower_ascii),
]
Rationale = Annotated[FreeText, Field(min_length=1, max_length=120)]
Confidence = Annotated[float, Field(ge=0, le=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Suggestion(_Strict):
    key: str = Field(pattern=KEY_PATTERN)
    parent: str = Field(pattern=REF_PATTERN)
    label: Label
    action: Action
    domain_key: DomainKey | None = Field(default=None, alias="domainKey")
    confidence: Confidence
    rationale: Rationale


class Link(_Strict):
    from_: str = Field(alias="from", pattern=REF_PATTERN)
    to: str = Field(pattern=REF_PATTERN)
    action: Action
    confidence: Confidence
    rationale: Rationale


class ConceptExpansionAnswer(_Strict):
    suggestions: list[Suggestion] = Field(max_length=MAX_ITEMS)
    links: list[Link] = Field(max_length=MAX_ITEMS)
