"""Text of an HTML page, paragraph by paragraph, read without running or fetching anything.

The page is tokenised by the standard library's HTML parser: no script runs, no stylesheet,
image, frame, font, base URL or link is fetched, and only the named and numeric character
references of HTML itself are decoded. The contents of `script`, `style`, `template`,
`noscript`, `iframe`, `object`, `embed`, `svg` and `math` are dropped. Block elements end a
paragraph. A page holds at most 5 MiB and nests at most 512 elements deep.
"""

from __future__ import annotations

from collections.abc import Callable
from html.parser import HTMLParser

from app.utilities.document_errors import DocumentTooLargeError

MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_DEPTH = 512

DROPPED = frozenset(
    {"script", "style", "template", "noscript", "iframe", "object", "embed", "svg", "math"}
)
BLOCKS = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "caption", "dd", "details",
        "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1",
        "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html", "li", "main",
        "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th",
        "thead", "title", "tr", "ul",
    }
)  # fmt: skip
VOID = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr",
    }
)  # fmt: skip


def html_paragraphs(data: bytes, text: str, count_chars: Callable[[int], None]) -> list[str]:
    """The paragraphs of a page, in document order; `data` are the uploaded bytes and `text`
    their decoded form."""
    if len(data) > MAX_HTML_BYTES:
        raise DocumentTooLargeError(
            f"the page is larger than {MAX_HTML_BYTES // (1024 * 1024)} MiB"
        )
    parser = _TextParser(count_chars)
    parser.feed(text)
    parser.close()
    parser.end_paragraph()
    return parser.paragraphs


class _TextParser(HTMLParser):
    def __init__(self, count_chars: Callable[[int], None]) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._current: list[str] = []
        self._open: list[str] = []
        self._dropping = 0
        self._count = count_chars

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCKS:
            self.end_paragraph()
        if tag in VOID:
            return
        self._open.append(tag)
        if len(self._open) > MAX_DEPTH:
            raise DocumentTooLargeError(f"the page nests more than {MAX_DEPTH} elements deep")
        if tag in DROPPED:
            self._dropping += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCKS:
            self.end_paragraph()

    def handle_endtag(self, tag: str) -> None:
        if tag in BLOCKS:
            self.end_paragraph()
        if tag not in self._open:
            return
        while self._open:
            closed = self._open.pop()
            if closed in DROPPED:
                self._dropping -= 1
            if closed == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._dropping or not data:
            return
        self._current.append(data)
        self._count(len(data))

    def end_paragraph(self) -> None:
        text = " ".join("".join(self._current).split())
        if text:
            self.paragraphs.append(text)
        self._current = []
