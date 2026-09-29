"""A bake-off document read from disk: its full plain text and what to upload for import.

Formats the import API reads natively and faithfully (txt, md, docx, text-layer pdf) upload the
original bytes under the original name. HTML, PowerPoint, Excel and scanned PDFs upload the
extracted text as a UTF-8 Markdown file named `<stem>.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrUsage:
    """What the OCR step cost for one document."""

    deployment: str
    pages: int
    latency_ms: int
    cost_eur: float


@dataclass
class LoadedDocument:
    path: Path
    format: str  # one of txt, md, html, docx, pdf, scanned_pdf, pptx, xlsx
    text: str  # full plain text, paragraphs separated by blank lines
    upload_name: str
    upload_bytes: bytes  # what to POST to /import/sentences
    ocr: OcrUsage | None = None
    pages: int | None = None
    words: int = 0
