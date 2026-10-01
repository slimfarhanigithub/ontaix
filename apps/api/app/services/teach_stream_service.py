"""`POST /teach/parse/stream`: a prepared parse answered as newline-delimited JSON events.

The parse runs as for `POST /teach/parse`, with its model answer streamed. When the grammar
read a typed sentence whole, its drafts are sent first, before the model answers. Each time a
part of the answer reads validly, the drafts the result would hold if the answer ended there are
compared with the drafts already sent, and each new one is sent once as a `draft` line, with the
next index. Two drafts are the same when they are equal, or when both are concept or spec
drafts of the same concept: the same company, label (singular or plural) and parent, so a
draft the model refines - another action or domain for the concept the grammar drafted - keeps
the cell already shown rather than adding a second one. When the parse ends, the sent drafts
the final result does not hold - every one of them when the whole answer is refused - are
named in one `retract` line, and the `result` line carries the body `POST /teach/parse`
answers. A parse that fails after the stream began ends with an `error` line instead. The
parse runs to its end even when the caller goes away, so the budget, the cost record and the
session turns are those of the plain endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.models.api.base import ApiModel
from app.models.api.teach import DraftNote
from app.models.api.teach_stream import (
    TeachDraftEvent,
    TeachErrorEvent,
    TeachResultEvent,
    TeachRetractEvent,
)
from app.services.teach_service import PreparedParse
from app.utilities.problems import ProblemError
from app.utilities.teach_parser import singular

logger = logging.getLogger(__name__)

MEDIA_TYPE = "application/x-ndjson"
CONCEPT_DRAFTS = frozenset({"concept", "spec"})
FAILED_DETAIL = "The sentence could not be read to the end; teach it again."

# Parses whose caller went away, kept until they end.
_detached: set[asyncio.Task[None]] = set()


async def events(prepared: PreparedParse) -> AsyncIterator[bytes]:
    """The parse's lines, each one JSON object and a line feed, as they become known."""
    lines: asyncio.Queue[bytes | None] = asyncio.Queue()
    sent: list[dict[str, Any]] = []

    async def on_drafts(drafts: list[dict[str, Any]], notes: list[DraftNote]) -> None:
        for i in unmatched(drafts, sent):
            sent.append(drafts[i])
            lines.put_nowait(
                _line(TeachDraftEvent(index=len(sent) - 1, draft=drafts[i], note=notes[i]))
            )

    async def run() -> None:
        try:
            result = await prepared.finish(on_drafts)
        except Exception:
            logger.exception("a streamed teach parse failed")
            problem = ProblemError(503, "unavailable", FAILED_DETAIL).body(None)
            lines.put_nowait(_line(TeachErrorEvent(problem=problem)))
        else:
            gone = unmatched(sent, result.drafts)
            if gone:
                lines.put_nowait(_line(TeachRetractEvent(indexes=gone)))
            lines.put_nowait(_line(TeachResultEvent(result=result)))
        finally:
            lines.put_nowait(None)

    task = asyncio.create_task(run(), name="teach-parse-stream")
    try:
        while (line := await lines.get()) is not None:
            yield line
    finally:
        if not task.done():
            _detached.add(task)
            task.add_done_callback(_detached.discard)


def unmatched(drafts: list[dict[str, Any]], among: list[dict[str, Any]]) -> list[int]:
    """The indexes of `drafts` with no draft of `among` that is the same (`same_draft`), in
    order; each draft of `among` matches one draft of `drafts` at most, an equal one first."""
    free = list(among)
    out: list[int] = []
    for i, draft in enumerate(drafts):
        match = next((d for d in free if d == draft), None) or next(
            (d for d in free if same_draft(d, draft)), None
        )
        if match is not None:
            free.remove(match)
        else:
            out.append(i)
    return out


def same_draft(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when the drafts are equal, or both are concept or spec drafts of one concept: the
    same type and company, the same label up to singular and plural, and the same parent."""
    if a == b:
        return True
    if a.get("type") != b.get("type") or a.get("type") not in CONCEPT_DRAFTS:
        return False
    return (
        a.get("companyId") == b.get("companyId")
        and _label_key(str(a.get("label", ""))) == _label_key(str(b.get("label", "")))
        and (a.get("parentId"), a.get("parentLabel")) == (b.get("parentId"), b.get("parentLabel"))
    )


def _label_key(label: str) -> str:
    return singular(label.strip().lower())


def _line(event: ApiModel) -> bytes:
    return (event.model_dump_json(by_alias=True) + "\n").encode("utf-8")
