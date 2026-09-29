"""Document text extraction for imports: pure transforms from uploaded bytes to sentences.

Text, Markdown, CSV and JSON are read as one text; Word documents paragraph by paragraph and PDF
documents page by page, so each sentence keeps where it was found. Nothing here touches the
network or the disk: a DOCX is opened as a ZIP archive in memory and its XML is parsed with no
DTD and no entity expansion; a PDF is read with pypdf.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import defusedxml.ElementTree as DefusedET
from defusedxml import DefusedXmlException
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000
MAX_SENTENCES = 2000
MAX_DOCX_MEMBERS = 1000
MAX_PDF_PAGES = 2000
MAX_DOCX_XML_BYTES = 64 * 1024 * 1024
MIN_SENTENCE_CHARS = 13
MAX_SENTENCE_CHARS = 399

TEXT_PLAIN = "text/plain"
TEXT_MARKDOWN = "text/markdown"
TEXT_CSV = "text/csv"
APPLICATION_JSON = "application/json"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"
MEDIA_TYPES = (TEXT_PLAIN, TEXT_MARKDOWN, TEXT_CSV, APPLICATION_JSON, DOCX, PDF)
MEDIA_TYPE_BY_EXTENSION = {
    ".txt": TEXT_PLAIN,
    ".text": TEXT_PLAIN,
    ".md": TEXT_MARKDOWN,
    ".markdown": TEXT_MARKDOWN,
    ".csv": TEXT_CSV,
    ".json": APPLICATION_JSON,
    ".docx": DOCX,
    ".pdf": PDF,
}

FILE_NAME_MAX_CHARS = 255
FILE_NAME_MAX_BYTES = 1020
REFUSED_FILE_NAME_CHARS = re.compile("[/\\\\:\x00-\x1f\x7f-\x9f‎‏‪-‮؜⁦-⁩﻿]")

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_BODY = "word/document.xml"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Sentence:
    text: str
    unit: str | None = None
    index: int | None = None


class DocumentTooLargeError(Exception):
    """The document passes one of the import limits."""


class DocumentUnreadableError(Exception):
    """The document is not a readable file of its media type."""


def file_name_problem(file_name: str) -> str | None:
    """Why a file name (already stripped of its directory part) is refused, or None."""
    if not file_name:
        return "the file name is empty"
    if len(file_name) > FILE_NAME_MAX_CHARS:
        return f"the file name is longer than {FILE_NAME_MAX_CHARS} characters"
    if len(file_name.encode("utf-8")) > FILE_NAME_MAX_BYTES:
        return f"the file name is longer than {FILE_NAME_MAX_BYTES} bytes"
    if REFUSED_FILE_NAME_CHARS.search(file_name):
        return "the file name holds a refused character"
    return None


def base_name(file_name: str) -> str:
    """The part after the last `/` or `\\`."""
    return re.split(r"[/\\]", file_name)[-1]


def media_type_of(file_name: str, declared: str | None) -> str | None:
    """The import media type by extension, else the declared one when it is supported."""
    dot = file_name.rfind(".")
    if dot >= 0:
        by_extension = MEDIA_TYPE_BY_EXTENSION.get(file_name[dot:].lower())
        if by_extension:
            return by_extension
    declared_type = (declared or "").split(";")[0].strip().lower()
    return declared_type if declared_type in MEDIA_TYPES else None


def extract_sentences(data: bytes, media_type: str) -> tuple[list[Sentence], int]:
    """The sentences of a document in order, and the number of extracted characters."""
    if media_type == DOCX:
        blocks = _docx_paragraphs(data)
        unit = "paragraph"
    elif media_type == PDF:
        blocks = _pdf_pages(data)
        unit = "page"
    else:
        text = data.decode("utf-8", errors="replace")
        if media_type == TEXT_CSV:
            text = _csv_text(text)
        _check_chars(len(text))
        blocks = [text]
        unit = None
    extracted = sum(len(b) for b in blocks)
    sentences: list[Sentence] = []
    for i, block in enumerate(blocks, start=1):
        for s in sentences_of(block):
            sentences.append(Sentence(s, unit, i if unit else None))
            if len(sentences) > MAX_SENTENCES:
                raise DocumentTooLargeError(f"more than {MAX_SENTENCES} sentences")
    return sentences, extracted


def sentences_of(text: str) -> list[str]:
    """Sentences of 13 to 399 characters, split on sentence punctuation or newlines."""
    parts = _SENTENCE_SPLIT.split(re.sub(r"\s+", " ", text))
    return [
        p for p in (x.strip() for x in parts) if MIN_SENTENCE_CHARS <= len(p) <= MAX_SENTENCE_CHARS
    ]


def _check_chars(count: int) -> None:
    if count > MAX_EXTRACTED_CHARS:
        raise DocumentTooLargeError(f"more than {MAX_EXTRACTED_CHARS} extracted characters")


def _csv_text(raw: str) -> str:
    """CSV rows become sentences: the non-empty cells of a row joined by spaces."""
    rows = re.split(r"\r?\n", raw)
    return ". ".join(
        " ".join(c for c in (cell.strip() for cell in re.split(r"[;,\t]", r)) if c) for r in rows
    )


class _CappedReader(io.RawIOBase):
    """Reads a decompressing stream and stops past `limit` bytes."""

    def __init__(self, stream: io.BufferedIOBase, limit: int) -> None:
        self._stream = stream
        self._left = limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        chunk = self._stream.read(min(len(buffer), 65536))
        self._left -= len(chunk)
        if self._left < 0:
            raise DocumentTooLargeError("the document body is too large once decompressed")
        buffer[: len(chunk)] = chunk
        return len(chunk)


def _docx_paragraphs(data: bytes) -> list[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentUnreadableError("the file is not a Word document") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_DOCX_MEMBERS:
            raise DocumentTooLargeError(f"more than {MAX_DOCX_MEMBERS} archive members")
        if DOCX_BODY not in archive.namelist():
            raise DocumentUnreadableError("the file is not a Word document")
        paragraphs: list[str] = []
        current: list[str] = []
        total = 0
        try:
            with archive.open(DOCX_BODY) as raw:
                stream = io.BufferedReader(_CappedReader(raw, MAX_DOCX_XML_BYTES))
                events = DefusedET.iterparse(
                    stream, events=("start", "end"), forbid_dtd=True, forbid_entities=True
                )
                for event, element in events:
                    tag = element.tag
                    if event == "start" and tag == f"{WORD_NS}p":
                        current = []
                    elif event != "end":
                        continue
                    elif tag == f"{WORD_NS}t" and element.text:
                        current.append(element.text)
                        total += len(element.text)
                        _check_chars(total)
                    elif tag == f"{WORD_NS}tab":
                        current.append("\t")
                    elif tag in (f"{WORD_NS}br", f"{WORD_NS}cr"):
                        current.append(" ")
                    elif tag == f"{WORD_NS}p":
                        text = "".join(current)
                        if text.strip():
                            paragraphs.append(text)
                        element.clear()
        except DefusedXmlException as exc:
            raise DocumentUnreadableError(
                "the Word document declares a DTD or entities, which are not read"
            ) from exc
        except (DefusedET.ParseError, zipfile.BadZipFile, EOFError, OSError) as exc:
            raise DocumentUnreadableError("the Word document could not be read") from exc
    return paragraphs


def _pdf_pages(data: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentUnreadableError("the PDF is encrypted")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentTooLargeError(f"more than {MAX_PDF_PAGES} pages")
        pages: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            total += len(text)
            _check_chars(total)
            pages.append(text)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise DocumentUnreadableError("the PDF could not be read") from exc
    return pages
