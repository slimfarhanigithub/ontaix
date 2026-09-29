"""Text of a PowerPoint deck: shape text and speaker notes, slide by slide, in slide order.

Slides are taken from the presentation's slide list, at most 500. A slide's text is the text of
its paragraphs followed by those of its speaker notes. Images, charts, embedded objects
and external links are never read.
"""

from __future__ import annotations

from collections.abc import Callable

from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.ooxml_archive import OoxmlArchive, office_relationship_id

MAX_SLIDES = 500

PRESENTATION_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NOTES_SLIDE_TYPE = "/notesSlide"


def slide_texts(archive: OoxmlArchive, count_chars: Callable[[int], None]) -> list[list[str]]:
    """The paragraphs of each slide, notes last, in slide order; `count_chars` is told every run
    of text read."""
    main = archive.main_part("pptx")
    if not archive.has(main):
        raise DocumentUnreadableError("the presentation has no slide list")
    targets = {rid: target for rid, target, _ in archive.relationships(main)}
    slide_ids: list[str] = []
    for event, element in archive.iterparse(main):
        if event == "end" and element.tag == f"{PRESENTATION_NS}sldId":
            rid = office_relationship_id(element)
            if rid:
                slide_ids.append(rid)
                if len(slide_ids) > MAX_SLIDES:
                    raise DocumentTooLargeError(f"more than {MAX_SLIDES} slides")
    texts: list[list[str]] = []
    for rid in slide_ids:
        slide = targets.get(rid)
        if slide is None or not archive.has(slide):
            texts.append([])
            continue
        lines = _paragraphs(archive, slide, count_chars)
        for _, target, kind in archive.relationships(slide):
            if kind.endswith(NOTES_SLIDE_TYPE) and archive.has(target):
                lines.extend(_paragraphs(archive, target, count_chars))
        texts.append(lines)
    return texts


def _paragraphs(archive: OoxmlArchive, part: str, count_chars: Callable[[int], None]) -> list[str]:
    """The text of every DrawingML paragraph of one part."""
    lines: list[str] = []
    current: list[str] = []
    for event, element in archive.iterparse(part):
        tag = element.tag
        if event == "start":
            if tag == f"{DRAWING_NS}p":
                current = []
            continue
        if tag == f"{DRAWING_NS}t" and element.text:
            current.append(element.text)
            count_chars(len(element.text))
        elif tag == f"{DRAWING_NS}br":
            current.append(" ")
        elif tag == f"{DRAWING_NS}p":
            text = "".join(current).strip()
            if text:
                lines.append(text)
    return lines
