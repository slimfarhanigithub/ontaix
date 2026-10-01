"""The lines of `POST /teach/parse/stream`: newline-delimited JSON, one event per line."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.models.api.base import ApiModel
from app.models.api.teach import DraftNote, TeachResult


class TeachDraftEvent(ApiModel):
    """A draft the valid part of the model's answer gives, sent once, as soon as it is known.
    `index` counts the stream's drafts from 0; the final result says which of them stand."""

    type: Literal["draft"] = "draft"
    index: int = Field(ge=0)
    draft: dict[str, Any]
    note: DraftNote


class TeachRetractEvent(ApiModel):
    """The streamed drafts the final result does not hold, all of them when the whole answer
    is refused; sent once, just before the result, when there is any."""

    type: Literal["retract"] = "retract"
    indexes: list[int]


class TeachResultEvent(ApiModel):
    """The last line of a parse: the body `POST /teach/parse` answers for the same request."""

    type: Literal["result"] = "result"
    result: TeachResult


class TeachErrorEvent(ApiModel):
    """The last line of a parse that failed after its stream began, in place of a `5xx`."""

    type: Literal["error"] = "error"
    problem: dict[str, Any]
