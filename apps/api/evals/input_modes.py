"""The ways a case reaches the teach pipeline, one pluggable mode per channel.

- `typed`: each turn of a text case is one typed sentence.
- `speech`: a spoken recording, sent as the Studio's microphone sends it: each finished
  sentence is one `speech` request, in order, in the recording's one session, and its drafts
  are proposed before the next sentence goes out, so back-references resolve.
- `sentences`: a document is imported (`POST /import/sentences`) and each stored sentence is
  parsed with its neighbours, in order, as the Studio's import panel does.
- `whole`: the whole document in one request. The endpoint is still being designed, so this
  mode reports itself unavailable; a case run in it is recorded as skipped.

A new mode implements `InputMode` and is added to `MODES`. Documents are read once per process
through `DocumentCache`, so an OCR step is paid and measured once, separately from the models.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from evals.doc_formats.loaded_document import LoadedDocument
from evals.doc_formats.loader import load_document
from evals.doc_formats.ocr_client import OcrClient
from evals.teach_case import CaseKind, TeachCase
from evals.workspace import UnitResult, Workspace

INLINE_DOCUMENT_SUFFIX = ".txt"


class ModeUnavailable(Exception):
    """The mode cannot run yet; the case is recorded as skipped with this reason."""


@dataclass
class ModeOutput:
    units: list[UnitResult]
    # The text the case's labels are grounded in.
    source_text: str
    document: dict[str, Any] | None = None


class InputMode(Protocol):
    name: str
    kind: CaseKind

    async def run(self, ws: Workspace, case: TeachCase, docs: DocumentCache) -> ModeOutput: ...


@dataclass
class DocumentCache:
    """Each document file read once (OCR included); inline documents need no reading."""

    ocr: OcrClient | None = None
    _loaded: dict[Path, LoadedDocument] = field(default_factory=dict)
    _locks: dict[Path, asyncio.Lock] = field(default_factory=dict)

    async def get(self, path: Path) -> LoadedDocument:
        lock = self._locks.setdefault(path, asyncio.Lock())
        async with lock:
            if path not in self._loaded:
                self._loaded[path] = await load_document(path, self.ocr)
            return self._loaded[path]

    def loaded(self) -> list[LoadedDocument]:
        return list(self._loaded.values())


class TypedMode:
    name = "typed"
    kind: CaseKind = "text"

    async def run(self, ws: Workspace, case: TeachCase, docs: DocumentCache) -> ModeOutput:
        units = [await ws.parse({"text": turn}) for turn in case.input]
        return ModeOutput(units, "\n".join(case.input))


class SpeechMode:
    name = "speech"
    kind: CaseKind = "speech"

    async def run(self, ws: Workspace, case: TeachCase, docs: DocumentCache) -> ModeOutput:
        units = [
            await ws.parse({"text": sentence.strip(), "origin": "speech"})
            for sentence in case.input
        ]
        return ModeOutput(units, "\n".join(case.input))


class SentencesMode:
    name = "sentences"
    kind: CaseKind = "document"

    async def run(self, ws: Workspace, case: TeachCase, docs: DocumentCache) -> ModeOutput:
        name, data, source_text, info = await _document(case, docs)
        import_id, count = await ws.upload(name, data)
        info["sentences"] = count
        units = [
            await ws.parse({"importRef": {"importId": import_id, "sentenceIndex": i}})
            for i in range(count)
        ]
        return ModeOutput(units, source_text, info)


class WholeDocumentMode:
    name = "whole"
    kind: CaseKind = "document"

    async def run(self, ws: Workspace, case: TeachCase, docs: DocumentCache) -> ModeOutput:
        raise ModeUnavailable("the whole-document teach endpoint is not implemented yet")


MODES: dict[str, InputMode] = {
    m.name: m for m in (TypedMode(), SpeechMode(), SentencesMode(), WholeDocumentMode())
}


def modes_for(case: TeachCase, document_modes: list[str]) -> list[InputMode]:
    if case.kind == "text":
        return [MODES["typed"]]
    if case.kind == "speech":
        return [MODES["speech"]]
    return [MODES[m] for m in document_modes]


async def document_text(case: TeachCase, docs: DocumentCache) -> str:
    """The case's full document text, for grounding and estimates."""
    if case.document is None:
        return "\n".join(case.input)
    return (await docs.get(case.document)).text


async def _document(case: TeachCase, docs: DocumentCache) -> tuple[str, bytes, str, dict[str, Any]]:
    if case.document is None:
        body = case.input[0]
        info: dict[str, Any] = {"format": "inline", "words": len(body.split())}
        return f"{case.id}{INLINE_DOCUMENT_SUFFIX}", body.encode("utf-8"), body, info
    loaded = await docs.get(case.document)
    info = {"format": loaded.format, "words": loaded.words, "pages": loaded.pages}
    return loaded.upload_name, loaded.upload_bytes, loaded.text, info
