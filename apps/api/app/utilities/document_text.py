"""Document text extraction for imports: pure transforms from uploaded bytes to sentences.

The type of an upload is decided from its bytes, and the type its name or header declares must
agree. Text, Markdown, CSV and JSON are read as one text; Word documents and HTML pages
paragraph by paragraph, PDF documents page by page, PowerPoint decks slide by slide and Excel
workbooks row by row, so each sentence keeps where it was found. A PDF page whose text layer
holds fewer than 20 non-space characters is image-only: its number is reported so the caller
can have it recognised, and its text is supplied before sentences are split. Nothing here
touches the network or the disk.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import LimitReachedError, PyPdfError

from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)
from app.utilities.html_text import html_paragraphs
from app.utilities.ooxml_archive import OoxmlArchive, ooxml_kind
from app.utilities.pptx_text import slide_texts
from app.utilities.xlsx_cells import sheet_rows

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000
MAX_SENTENCES = 2000
MAX_PDF_PAGES = 2000
MIN_SENTENCE_CHARS = 13
MAX_SENTENCE_CHARS = 399
# A PDF page with fewer non-space characters than this in its text layer is image-only.
MIN_TEXT_LAYER_CHARS = 20

TEXT_PLAIN = "text/plain"
TEXT_MARKDOWN = "text/markdown"
TEXT_CSV = "text/csv"
APPLICATION_JSON = "application/json"
TEXT_HTML = "text/html"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
TEXT_TYPES = (TEXT_PLAIN, TEXT_MARKDOWN, TEXT_CSV, APPLICATION_JSON)
MEDIA_TYPES = (*TEXT_TYPES, DOCX, PDF, PPTX, XLSX, TEXT_HTML)
MEDIA_TYPE_BY_EXTENSION = {
    ".txt": TEXT_PLAIN,
    ".text": TEXT_PLAIN,
    ".md": TEXT_MARKDOWN,
    ".markdown": TEXT_MARKDOWN,
    ".csv": TEXT_CSV,
    ".json": APPLICATION_JSON,
    ".docx": DOCX,
    ".pdf": PDF,
    ".pptx": PPTX,
    ".xlsx": XLSX,
    ".html": TEXT_HTML,
    ".htm": TEXT_HTML,
}
MEDIA_TYPE_BY_OOXML_KIND = {"docx": DOCX, "pptx": PPTX, "xlsx": XLSX}

FILE_NAME_MAX_CHARS = 255
FILE_NAME_MAX_BYTES = 1020
REFUSED_FILE_NAME_CHARS = re.compile(
    "[/\\\\:\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]"
)

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

ZIP_SIGNATURE = b"PK\x03\x04"
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PDF_SIGNATURE = b"%PDF-"
PDF_SIGNATURE_WINDOW = 1024
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
HTML_STARTS = ("<!doctype html", "<html", "<head", "<body")
SNIFFED_TEXT = "text"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)


@dataclass(frozen=True)
class Sentence:
    text: str
    unit: str | None = None
    index: int | None = None
    row: int | None = None


@dataclass(frozen=True)
class TextBlock:
    """A run of extracted text and where it was found. A `whole` block is one sentence as it
    stands (a spreadsheet row) and is never split."""

    text: str
    unit: str | None = None
    index: int | None = None
    row: int | None = None
    whole: bool = False


@dataclass(frozen=True)
class ExtractedDocument:
    """The blocks of a document; for a PDF, `image_pages` are the 1-based image-only pages,
    whose blocks are empty until their recognised text is supplied."""

    blocks: list[TextBlock]
    image_pages: list[int] = field(default_factory=list)


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
    """The declared import media type: by extension, else the header when it is supported."""
    dot = file_name.rfind(".")
    if dot >= 0:
        by_extension = MEDIA_TYPE_BY_EXTENSION.get(file_name[dot:].lower())
        if by_extension:
            return by_extension
    declared_type = (declared or "").split(";")[0].strip().lower()
    return declared_type if declared_type in MEDIA_TYPES else None


def sniff(data: bytes) -> str:
    """The type the bytes are: `application/pdf`, an OOXML type, `text/html`, or `text` for any
    other UTF-8 (or UTF-16 with a byte order mark) text. Raises `UnsupportedDocumentError`
    for legacy or encrypted Office files, macro-enabled or unknown archives, and binary data."""
    if data.startswith(OLE_SIGNATURE):
        raise UnsupportedDocumentError(
            "legacy binary and encrypted Office documents are not read; save it as DOCX, PPTX "
            "or XLSX"
        )
    if PDF_SIGNATURE in data[:PDF_SIGNATURE_WINDOW]:
        return PDF
    if data.startswith(ZIP_SIGNATURE):
        return MEDIA_TYPE_BY_OOXML_KIND[ooxml_kind(data)]
    try:
        text = decode_text(data)
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("the file is not UTF-8 text") from exc
    head = text[:1024].lstrip().lower()
    return TEXT_HTML if head.startswith(HTML_STARTS) else SNIFFED_TEXT


def agreed_media_type(declared: str, data: bytes) -> str:
    """The sniffed media type when it agrees with the declared one; `UnsupportedDocumentError`
    otherwise. Any declared text type agrees with sniffed text."""
    sniffed = sniff(data)
    if sniffed == SNIFFED_TEXT and declared in TEXT_TYPES:
        return declared
    if sniffed == declared:
        return sniffed
    raise UnsupportedDocumentError(
        f"the file is {_type_name(sniffed)} but its name or type says {_type_name(declared)}"
    )


def decode_text(data: bytes) -> str:
    """Text bytes as a string: UTF-16 when a UTF-16 byte order mark leads, else UTF-8 with an
    optional byte order mark."""
    if data.startswith(UTF16_BOMS):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def extract_document(data: bytes, media_type: str) -> ExtractedDocument:
    """The text blocks of a document in order, bounded by the extracted-text limit."""
    counter = _CharCounter()
    if media_type == DOCX:
        with OoxmlArchive(data, "the Word document") as archive:
            paragraphs = _docx_paragraphs(archive, counter)
        return ExtractedDocument(_numbered(paragraphs, "paragraph"))
    if media_type == PPTX:
        with OoxmlArchive(data, "the presentation") as archive:
            slides = slide_texts(archive, counter)
        return ExtractedDocument(
            [
                TextBlock(line, "slide", i)
                for i, lines in enumerate(slides, start=1)
                for line in lines
            ]
        )
    if media_type == XLSX:
        with OoxmlArchive(data, "the workbook") as archive:
            rows = [
                TextBlock(
                    ", ".join(r.cells[c] for c in sorted(r.cells)), "sheet", r.sheet, r.row, True
                )
                for r in sheet_rows(archive, count_chars=counter)
            ]
        return ExtractedDocument(rows)
    if media_type == PDF:
        return _pdf_pages(data, counter)
    text = decode_text(data)
    if media_type == TEXT_HTML:
        return ExtractedDocument(_numbered(html_paragraphs(data, text, counter), "paragraph"))
    if media_type == TEXT_CSV:
        text = _csv_text(text)
    counter(len(text))
    return ExtractedDocument([TextBlock(text)])


def with_recognised_pages(document: ExtractedDocument, pages: dict[int, str]) -> ExtractedDocument:
    """The document with the recognised text of its image-only pages in place, in page order."""
    counter = _CharCounter(sum(len(b.text) for b in document.blocks))
    blocks = []
    for block in document.blocks:
        if block.unit == "page" and block.index in pages:
            text = recognised_text(pages[block.index])
            counter(len(text))
            block = TextBlock(text, "page", block.index)
        blocks.append(block)
    return ExtractedDocument(blocks)


def recognised_text(markdown: str) -> str:
    """The text of one recognised page, given as Markdown: image references and heading marks
    are dropped and table bars read as spaces."""
    text = _MARKDOWN_HEADING.sub("", _MARKDOWN_IMAGE.sub(" ", markdown))
    return text.replace("|", " ")


def sentences_of_document(document: ExtractedDocument) -> tuple[list[Sentence], int]:
    """The sentences of a document in order, and the number of extracted characters."""
    extracted = sum(len(b.text) for b in document.blocks)
    sentences: list[Sentence] = []
    for block in document.blocks:
        texts = [_whole_sentence(block.text)] if block.whole else sentences_of(block.text)
        for text in texts:
            if text is None:
                continue
            sentences.append(Sentence(text, block.unit, block.index, block.row))
            if len(sentences) > MAX_SENTENCES:
                raise DocumentTooLargeError(f"more than {MAX_SENTENCES} sentences")
    return sentences, extracted


def extract_sentences(data: bytes, media_type: str) -> tuple[list[Sentence], int]:
    """The sentences of a document and its extracted characters; image-only PDF pages add
    nothing."""
    return sentences_of_document(extract_document(data, media_type))


def sentences_of(text: str) -> list[str]:
    """Sentences of 13 to 399 characters, split on sentence punctuation or newlines."""
    parts = _SENTENCE_SPLIT.split(re.sub(r"\s+", " ", text))
    return [
        p for p in (x.strip() for x in parts) if MIN_SENTENCE_CHARS <= len(p) <= MAX_SENTENCE_CHARS
    ]


def _whole_sentence(text: str) -> str | None:
    collapsed = " ".join(text.split())
    return collapsed if MIN_SENTENCE_CHARS <= len(collapsed) <= MAX_SENTENCE_CHARS else None


def _numbered(texts: list[str], unit: str) -> list[TextBlock]:
    return [TextBlock(t, unit, i) for i, t in enumerate(texts, start=1) if t.strip()]


def _type_name(media_type: str) -> str:
    names = {
        SNIFFED_TEXT: "text",
        TEXT_PLAIN: "text",
        TEXT_MARKDOWN: "Markdown",
        TEXT_CSV: "CSV",
        APPLICATION_JSON: "JSON",
        TEXT_HTML: "HTML",
        DOCX: "a Word document",
        PPTX: "a PowerPoint presentation",
        XLSX: "an Excel workbook",
        PDF: "a PDF",
    }
    return names.get(media_type, media_type)


class _CharCounter:
    """Counts extracted characters and stops past the extracted-text limit."""

    def __init__(self, start: int = 0) -> None:
        self.total = start

    def __call__(self, count: int) -> None:
        self.total += count
        if self.total > MAX_EXTRACTED_CHARS:
            raise DocumentTooLargeError(f"more than {MAX_EXTRACTED_CHARS} extracted characters")


def _csv_text(raw: str) -> str:
    """CSV rows become sentences: the non-empty cells of a row joined by spaces."""
    rows = re.split(r"\r?\n", raw)
    return ". ".join(
        " ".join(c for c in (cell.strip() for cell in re.split(r"[;,\t]", r)) if c) for r in rows
    )


def _docx_paragraphs(archive: OoxmlArchive, count_chars: Callable[[int], None]) -> list[str]:
    body = archive.main_part("docx")
    if not archive.has(body):
        raise DocumentUnreadableError("the file is not a Word document")
    paragraphs: list[str] = []
    current: list[str] = []
    for event, element in archive.iterparse(body):
        tag = element.tag
        if event == "start":
            if tag == f"{WORD_NS}p":
                current = []
            continue
        if tag == f"{WORD_NS}t" and element.text:
            current.append(element.text)
            count_chars(len(element.text))
        elif tag == f"{WORD_NS}tab":
            current.append("\t")
        elif tag in (f"{WORD_NS}br", f"{WORD_NS}cr"):
            current.append(" ")
        elif tag == f"{WORD_NS}p":
            text = "".join(current)
            if text.strip():
                paragraphs.append(text)
    return paragraphs


def _pdf_pages(data: bytes, count_chars: Callable[[int], None]) -> ExtractedDocument:
    """Page texts from the text layer; attachments, forms and scripts are never read or run."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentUnreadableError("the PDF is encrypted")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentTooLargeError(f"more than {MAX_PDF_PAGES} pages")
        blocks: list[TextBlock] = []
        image_pages: list[int] = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if len("".join(text.split())) < MIN_TEXT_LAYER_CHARS:
                image_pages.append(number)
                text = ""
            count_chars(len(text))
            blocks.append(TextBlock(text, "page", number))
    except LimitReachedError as exc:
        raise DocumentTooLargeError("the PDF is too large once decompressed") from exc
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise DocumentUnreadableError("the PDF could not be read") from exc
    return ExtractedDocument(blocks, image_pages)
