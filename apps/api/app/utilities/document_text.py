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

from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError, PyPdfError
from pypdf.generic import NameObject

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
    # A PDF of the image-only pages alone, in the order of `image_pages`: all that OCR receives.
    image_pdf: bytes | None = None


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
    are dropped; line breaks stay, so headings, list items and table rows keep their own
    sentences."""
    return _MARKDOWN_HEADING.sub("", _MARKDOWN_IMAGE.sub(" ", markdown))


def sentences_of_document(document: ExtractedDocument) -> tuple[list[Sentence], int, int]:
    """The sentences of a document in order, the number of extracted characters, and the number
    of text pieces left out as shorter than 13 characters. A spreadsheet row is one sentence,
    cut only when it passes 399 characters."""
    extracted = sum(len(b.text) for b in document.blocks)
    sentences: list[Sentence] = []
    skipped = 0
    for block in document.blocks:
        if block.whole:
            pieces = _fit(" ".join(block.text.split()))
            kept = [p for p in pieces if len(p) >= MIN_SENTENCE_CHARS]
            left_out = sum(
                1 for p in pieces if len(p) < MIN_SENTENCE_CHARS and any(c.isalnum() for c in p)
            )
        else:
            kept, left_out = split_sentences(block.text)
        skipped += left_out
        for text in kept:
            sentences.append(Sentence(text, block.unit, block.index, block.row))
            if len(sentences) > MAX_SENTENCES:
                raise DocumentTooLargeError(f"more than {MAX_SENTENCES} sentences")
    return sentences, extracted, skipped


def extract_sentences(data: bytes, media_type: str) -> tuple[list[Sentence], int, int]:
    """The sentences, extracted characters and pieces left out of a document; image-only PDF
    pages add nothing."""
    return sentences_of_document(extract_document(data, media_type))


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
    start, end = 0, len(sentence)
    # The cuts walk an index through `sentence`, so a long text is never copied once per cut.
    while end - start > MAX_SENTENCE_CHARS:
        # Both sides of a cut keep at least 13 characters once the space at the cut is dropped,
        # so neither is left out.
        limit = min(MAX_SENTENCE_CHARS, end - start - MIN_SENTENCE_CHARS - 1)
        window_end = start + limit + 1
        cut = 0
        for pattern in _CLAUSE_ENDS:
            ends = [m.start() + 1 for m in pattern.finditer(sentence, start, window_end)]
            ends = [e for e in ends if start + MIN_SENTENCE_CHARS <= e <= start + limit]
            if ends:
                cut = ends[-1]
                break
        if not cut:
            space = sentence.rfind(" ", start + MIN_SENTENCE_CHARS, window_end)
            cut = space if space > 0 else start + limit
        pieces.append(sentence[start:cut].strip())
        start = cut
        while start < end and sentence[start].isspace():
            start += 1
    if start < end:
        pieces.append(sentence[start:end])
    return pieces


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
        image_pdf = _pages_only(reader, image_pages) if image_pages else None
    except LimitReachedError as exc:
        raise DocumentTooLargeError("the PDF is too large once decompressed") from exc
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise DocumentUnreadableError("the PDF could not be read") from exc
    return ExtractedDocument(blocks, image_pages, image_pdf)


# Page entries that can carry actions, links, attachments or form fields; none is copied.
_PAGE_KEYS_DROPPED = ("/Annots", "/AA")


def _pages_only(reader: PdfReader, numbers: list[int]) -> bytes:
    """A new PDF holding only the given 1-based pages, their content and resources, without
    annotations, actions, attachments, outlines or document-level scripts."""
    writer = PdfWriter()
    for number in numbers:
        page = writer.add_page(reader.pages[number - 1])
        for key in _PAGE_KEYS_DROPPED:
            if key in page:
                del page[NameObject(key)]
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
