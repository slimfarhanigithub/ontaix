"""Bounded reading of OOXML archives (DOCX, PPTX, XLSX): members, relationships and XML parts.

An archive holds at most 1,000 members. Decompression is counted in bytes while it streams,
whatever sizes the archive declares: each member at most 50 MiB, the archive at most 200 MiB in
total, and a member that inflates past 100 times its compressed size is refused. Every XML part
is parsed with no DTD, no entity expansion and no external reference, and at most 1,000,000
elements per part; finished elements are released as the parse goes, so the tree never grows.
The kind of an archive is decided by its `[Content_Types].xml`: exactly one DOCX, PPTX or XLSX
main part, never a macro-enabled content type or a `vbaProject.bin` part.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from collections.abc import Iterator
from typing import Any, Literal

import defusedxml.ElementTree as DefusedET
from defusedxml import DefusedXmlException

from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)

MAX_MEMBERS = 1000
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_XML_ELEMENTS = 1_000_000
READ_CHUNK = 65536

CONTENT_TYPES_PART = "[Content_Types].xml"
CONTENT_TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
PACKAGE_RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_RELS_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

OoxmlKind = Literal["docx", "pptx", "xlsx"]

MAIN_CONTENT_TYPES: dict[str, OoxmlKind] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": "xlsx",
}
DEFAULT_MAIN_PARTS: dict[OoxmlKind, str] = {
    "docx": "word/document.xml",
    "pptx": "ppt/presentation.xml",
    "xlsx": "xl/workbook.xml",
}
# Main parts of other Office documents (templates, add-ins, macro-enabled files and the like):
# a content type ending like this names a main part even when it is not one Ontaix reads.
_MAIN_SUFFIX = ".main+xml"
_MACRO_MARK = "macroenabled"
_VBA_PROJECT = "vbaproject.bin"


class OoxmlArchive:
    """One OOXML archive opened in memory, with every read counted against the bounds."""

    def __init__(self, data: bytes, what: str = "the document") -> None:
        self._what = what
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
            raise DocumentUnreadableError(f"{what} is not a readable Office file") from exc
        self._infos = self._zip.infolist()
        if len(self._infos) > MAX_MEMBERS:
            raise DocumentTooLargeError(f"more than {MAX_MEMBERS} archive members")
        self._by_name = {info.filename: info for info in self._infos}
        self._inflated = 0

    def __enter__(self) -> OoxmlArchive:
        return self

    def __exit__(self, *_: object) -> None:
        self._zip.close()

    @property
    def names(self) -> list[str]:
        return [info.filename for info in self._infos]

    def has(self, name: str) -> bool:
        return name in self._by_name

    def read(self, name: str) -> bytes:
        """The whole member, inflated within the bounds."""
        with self.open(name) as stream:
            return stream.read()

    def open(self, name: str) -> io.BufferedReader:
        """A stream of the member that stops at the member, archive and ratio bounds."""
        info = self._by_name.get(name)
        if info is None:
            raise DocumentUnreadableError(f"{self._what} has no part {name}")
        try:
            raw = self._zip.open(info)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
            raise DocumentUnreadableError(f"{self._what} could not be read") from exc
        return io.BufferedReader(_BoundedMember(raw, info, self))

    def iterparse(
        self, name: str, element_limit: int = MAX_XML_ELEMENTS
    ) -> Iterator[tuple[str, Any]]:
        """`("start" | "end", element)` of one XML part, parsed safely and released as it goes.

        A finished element is cleared and detached from its parent once the caller has seen its
        `end` event, so the caller reads an element's text and children at `end` only.
        """
        parents: list[Any] = []
        elements = 0
        try:
            with self.open(name) as stream:
                events = DefusedET.iterparse(
                    stream,
                    events=("start", "end"),
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True,
                )
                for event, element in events:
                    if event == "start":
                        elements += 1
                        if elements > element_limit:
                            raise DocumentTooLargeError(
                                f"more than {element_limit} elements in one part of {self._what}"
                            )
                        parents.append(element)
                        yield event, element
                        continue
                    parents.pop()
                    yield event, element
                    element.clear()
                    if parents:
                        parents[-1].remove(element)
        except DefusedXmlException as exc:
            raise DocumentUnreadableError(
                f"{self._what} declares a DTD or entities, which are not read"
            ) from exc
        except (DefusedET.ParseError, zipfile.BadZipFile, EOFError, OSError) as exc:
            raise DocumentUnreadableError(f"{self._what} could not be read") from exc

    def relationships(self, part: str) -> list[tuple[str, str, str]]:
        """`(id, target part name, type)` of one part's internal relationships, in file order."""
        rels = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
        if not self.has(rels):
            return []
        out: list[tuple[str, str, str]] = []
        for event, element in self.iterparse(rels):
            if event == "end" and element.tag == f"{PACKAGE_RELS_NS}Relationship":
                if element.get("TargetMode") == "External":
                    continue
                rid, target = element.get("Id"), element.get("Target")
                if rid and target:
                    out.append((rid, resolve_target(part, target), element.get("Type") or ""))
        return out

    def main_part(self, kind: OoxmlKind) -> str:
        """The main part's name from `[Content_Types].xml`, else the usual name for the kind."""
        for part, content_type in self.content_types().items():
            if MAIN_CONTENT_TYPES.get(content_type) == kind:
                return part
        return DEFAULT_MAIN_PARTS[kind]

    def content_types(self) -> dict[str, str]:
        """Part name (no leading `/`) to content type, from the `Override` entries."""
        if not self.has(CONTENT_TYPES_PART):
            return {}
        out: dict[str, str] = {}
        for event, element in self.iterparse(CONTENT_TYPES_PART):
            if event == "end" and element.tag == f"{CONTENT_TYPES_NS}Override":
                part, content_type = element.get("PartName"), element.get("ContentType")
                if part and content_type:
                    out[part.lstrip("/")] = content_type.strip().lower()
        return out

    def _count(self, size: int) -> None:
        self._inflated += size
        if self._inflated > MAX_ARCHIVE_BYTES:
            raise DocumentTooLargeError(
                f"{self._what} is larger than {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB "
                "once decompressed"
            )


def ooxml_kind(data: bytes) -> OoxmlKind:
    """The kind of an OOXML upload, or `UnsupportedDocumentError` when it is not exactly one
    DOCX, PPTX or XLSX main part, holds macros, or is not an Office archive at all."""
    try:
        archive = OoxmlArchive(data)
    except DocumentUnreadableError as exc:
        raise UnsupportedDocumentError(
            "the file is a ZIP archive but not an Office document"
        ) from exc
    with archive:
        if any(posixpath.basename(n).lower() == _VBA_PROJECT for n in archive.names):
            raise UnsupportedDocumentError("Office documents with macros are not read")
        content_types = archive.content_types()
        if any(_MACRO_MARK in t for t in content_types.values()):
            raise UnsupportedDocumentError("Office documents with macros are not read")
        mains = [t for t in content_types.values() if t.endswith(_MAIN_SUFFIX)]
        kinds = [MAIN_CONTENT_TYPES.get(t) for t in mains]
        if len(kinds) != 1 or kinds[0] is None:
            raise UnsupportedDocumentError(
                "the archive is not one Word, PowerPoint or Excel document"
            )
        return kinds[0]


def resolve_target(source_part: str, target: str) -> str:
    """A relationship target as a part name: absolute targets from the root, others relative to
    the source part's folder."""
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def office_relationship_id(element: Any) -> str | None:
    """The `r:id` attribute of an element."""
    return element.get(f"{OFFICE_RELS_NS}id")


class _BoundedMember(io.RawIOBase):
    """Reads an inflating member and stops at the member, archive and ratio bounds."""

    def __init__(self, stream: Any, info: zipfile.ZipInfo, archive: OoxmlArchive) -> None:
        self._stream = stream
        self._name = info.filename
        self._ratio_limit = MAX_COMPRESSION_RATIO * max(info.compress_size, 1)
        self._read = 0
        self._archive = archive

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self._stream.close()
        super().close()

    def readinto(self, buffer: Any) -> int:
        chunk = self._stream.read(min(len(buffer), READ_CHUNK))
        self._read += len(chunk)
        if self._read > MAX_MEMBER_BYTES:
            raise DocumentTooLargeError(
                f"an archive member is larger than {MAX_MEMBER_BYTES // (1024 * 1024)} MiB "
                "once decompressed"
            )
        if self._read > self._ratio_limit:
            raise DocumentTooLargeError(
                f"an archive member inflates more than {MAX_COMPRESSION_RATIO} times"
            )
        self._archive._count(len(chunk))
        buffer[: len(chunk)] = chunk
        return len(chunk)
