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
from pypdf.errors import LimitReachedError, PyPdfError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000
MAX_SENTENCES = 2000
MAX_DOCX_MEMBERS = 1000
MAX_PDF_PAGES = 2000
MAX_DOCX_XML_BYTES = 64 * 1024 * 1024
MAX_DOCX_XML_ELEMENTS = 1_000_000
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
REFUSED_FILE_NAME_CHARS = re.compile(
    "[/\\\\:\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]"
)

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_BODY = "word/document.xml"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
# A Markdown heading, a bullet or numbered list item, or a table row sits on a line of its own.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+•‣⁃–▪◦]|\d{1,3}[.)]|[a-zA-Z][.)])\s")
_TABLE_ROW = re.compile(r"^\s*\||\t")
_UNDERLINE = re.compile(r"^\s*(?:=+|-+)\s*$")
# Clause boundaries a long sentence is cut after, in order of preference.
_CLAUSE_ENDS = (
    re.compile(r"[;:]\s"),
    re.compile(r",\s(?=(?:and|or|but|so|yet|nor|while|whereas|because|which|including)\b)"),
)


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


ZIP_SIGNATURE = b"PK\x03\x04"
PDF_SIGNATURE = b"%PDF-"
PDF_SIGNATURE_WINDOW = 1024


def content_mismatch(data: bytes, media_type: str) -> str | None:
    """Why the bytes are not a file of `media_type`, or None: a Word document is a ZIP archive,
    a PDF carries its signature in its first kilobyte, and a text type is UTF-8 that is neither."""
    if media_type == DOCX:
        return None if data.startswith(ZIP_SIGNATURE) else "the file is not a Word document"
    if media_type == PDF:
        return None if PDF_SIGNATURE in data[:PDF_SIGNATURE_WINDOW] else "the file is not a PDF"
    if data.startswith(ZIP_SIGNATURE) or PDF_SIGNATURE in data[:PDF_SIGNATURE_WINDOW]:
        return "the file is a Word or PDF document, not text"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "the file is not UTF-8 text"
    return None


def extract_sentences(data: bytes, media_type: str) -> tuple[list[Sentence], int, int]:
    """The sentences of a document in order, the number of extracted characters, and the number
    of text pieces left out as shorter than 13 characters."""
    if media_type == DOCX:
        blocks = _docx_paragraphs(data)
        unit = "paragraph"
    elif media_type == PDF:
        blocks = _pdf_pages(data)
        unit = "page"
    else:
        text = data.decode("utf-8-sig", errors="replace")
        if media_type == TEXT_CSV:
            text = _csv_text(text)
        _check_chars(len(text))
        blocks = [text]
        unit = None
    extracted = sum(len(b) for b in blocks)
    sentences: list[Sentence] = []
    skipped = 0
    for i, block in enumerate(blocks, start=1):
        kept, left_out = split_sentences(block)
        skipped += left_out
        for s in kept:
            sentences.append(Sentence(s, unit, i if unit else None))
            if len(sentences) > MAX_SENTENCES:
                raise DocumentTooLargeError(f"more than {MAX_SENTENCES} sentences")
    return sentences, extracted, skipped


def sentences_of(text: str) -> list[str]:
    """Sentences of 13 to 399 characters, in order; see `split_sentences`."""
    return split_sentences(text)[0]


def split_sentences(text: str) -> tuple[list[str], int]:
    """Sentences of 13 to 399 characters, in order, and the number of pieces left out.

    The text is first cut into blocks at the line breaks that end something: a blank line, a
    heading, a list item or a table row. A line break that only wraps a paragraph is a space.
    Each block is split on sentence punctuation, and a sentence longer than 399 characters is
    cut after a clause boundary (`;`, `:`, or a comma before a conjunction), else at the last
    space, else at 399 characters, so no text is lost to the length limit. Pieces shorter than
    13 characters are left out and counted when they hold a letter or a digit; a table rule
    such as `|---|` holds neither."""
    parts: list[str] = []
    for block in _blocks(text):
        flat = re.sub(r"\s+", " ", block).strip()
        # A list marker such as `1.` stays with the item's first sentence.
        marker = _LIST_ITEM.match(flat)
        lead = flat[: marker.end()] if marker else ""
        sentences = _SENTENCE_SPLIT.split(flat[len(lead) :])
        sentences[0] = lead + sentences[0]
        for sentence in sentences:
            parts.extend(_fit(sentence.strip()))
    kept = [p for p in parts if len(p) >= MIN_SENTENCE_CHARS]
    left_out = sum(1 for p in parts if len(p) < MIN_SENTENCE_CHARS and any(c.isalnum() for c in p))
    return kept, left_out


def _blocks(text: str) -> list[str]:
    """The text cut at blank lines and around headings, list items and table rows; the other
    line breaks stay inside a block."""
    blocks: list[str] = []
    current: list[str] = []

    def close() -> None:
        if current:
            blocks.append(" ".join(current))
            current.clear()

    for line in re.split(r"\r\n|\r|\n", text):
        if not line.strip() or _UNDERLINE.match(line):
            close()
            continue
        if _HEADING.match(line) or _TABLE_ROW.search(line):
            close()
            blocks.append(line)
            continue
        if _LIST_ITEM.match(line):
            close()
        current.append(line)
    close()
    return blocks


def _fit(sentence: str) -> list[str]:
    """`sentence` in pieces of at most 399 characters, each cut at the best boundary before the
    limit; only the whitespace at a cut is dropped."""
    pieces: list[str] = []
    rest = sentence
    while len(rest) > MAX_SENTENCE_CHARS:
        # Both sides of a cut keep at least 13 characters, so neither is left out.
        limit = min(MAX_SENTENCE_CHARS, len(rest) - MIN_SENTENCE_CHARS)
        window = rest[: limit + 1]
        cut = 0
        for pattern in _CLAUSE_ENDS:
            ends = [m.start() + 1 for m in pattern.finditer(window)]
            ends = [e for e in ends if MIN_SENTENCE_CHARS <= e <= limit]
            if ends:
                cut = ends[-1]
                break
        if not cut:
            space = window.rfind(" ", MIN_SENTENCE_CHARS)
            cut = space if space > 0 else limit
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


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
                parents: list = []
                elements = 0
                for event, element in events:
                    if event == "start":
                        elements += 1
                        if elements > MAX_DOCX_XML_ELEMENTS:
                            raise DocumentTooLargeError(
                                f"more than {MAX_DOCX_XML_ELEMENTS} elements in the Word document"
                            )
                        if element.tag == f"{WORD_NS}p":
                            current = []
                        parents.append(element)
                        continue
                    parents.pop()
                    tag = element.tag
                    if tag == f"{WORD_NS}t" and element.text:
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
                    _release(element, parents)
        except DefusedXmlException as exc:
            raise DocumentUnreadableError(
                "the Word document declares a DTD or entities, which are not read"
            ) from exc
        except (DefusedET.ParseError, zipfile.BadZipFile, EOFError, OSError) as exc:
            raise DocumentUnreadableError("the Word document could not be read") from exc
    return paragraphs


def _release(element, parents: list) -> None:
    """Drop a finished element and its children, so the parsed tree never grows."""
    element.clear()
    if parents:
        parents[-1].remove(element)


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
    except LimitReachedError as exc:
        raise DocumentTooLargeError("the PDF is too large once decompressed") from exc
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise DocumentUnreadableError("the PDF could not be read") from exc
    return pages
