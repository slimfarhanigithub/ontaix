"""A specification's HTML page as plain Markdown prose, for use as a bake-off document.

Headings become `#` lines; paragraphs, list items, definition terms and descriptions, and table
cells become lines of text. Navigation, the table of contents, scripts, styles, images, code
blocks (`pre`), element metadata boxes and share buttons are dropped, so what is
left is the prose that defines things. Whitespace is collapsed and bare URLs are removed.

Run: `uv run python -m evals.html_to_text <in.html> <out.md>`.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

_SKIPPED_TAGS = frozenset(
    {"script", "style", "nav", "head", "pre", "img", "svg", "button", "form", "noscript"}
)
# Classes of navigation and metadata blocks in W3C and GoodRelations specifications.
_SKIPPED_CLASSES = frozenset(
    {
        "rdf_type",
        "item_list",
        "toc",
        "tocline",
        "tocxref",
        "head",
        "left_align",
        "ask_a_q_show",
        "ask_a_q_hide",
        "hidden_box",
        "ask_a_question_content",
        "window_open",
        "comment_p1",
        "bibref",
        "copyright",
    }
)
# Sections about the document rather than the vocabulary: status, contents, references, credits.
_SKIPPED_IDS = frozenset(
    {
        "sotd",
        "toc",
        "references",
        "acknowledgements",
        "acknowledgments",
        "change-history",
        "changes",
    }
)
_BLOCKS = frozenset(
    {
        "p",
        "li",
        "dt",
        "dd",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "div",
        "section",
        "tr",
        "br",
        "blockquote",
        "caption",
        "figcaption",
    }
)
_VOID = frozenset({"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr"})
_URL = re.compile(r"https?://\S+")
_RDF_TYPE = re.compile(r"\(rdf:type [^)]*\)")
_BARE_TERM = re.compile(r"[\w.-]+:[\w.-]+(\s*,\s*[\w.-]+:[\w.-]+)*")
_BOILERPLATE = frozenset(
    {
        "[back to top]",
        "back to top",
        "click here for additional resource",
        "discussions and links",
        "example",
        "examples",
        "table of contents",
        "microdata (schema.org)",
        "rdfa",
        "turtle",
        "uri",
        "predefined individuals",
    }
)
_BOILERPLATE_PREFIXES = (
    "click here for additional resource",
    "there is currently no example available",
    "please use the 'ask' button",
    "rdfs:label ",
    "rdfs:comment",
)
_SPACES = re.compile(r"\s+")


def html_to_markdown(html: str) -> str:
    parser = _Prose()
    parser.feed(html)
    parser.close()
    return parser.text()


class _Prose(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool]] = []
        self._lines: list[str] = []
        self._current: list[str] = []
        self._heading: int | None = None
        self._list_item = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        skip = (
            tag in _SKIPPED_TAGS
            or bool(classes & _SKIPPED_CLASSES)
            or (attributes.get("id") or "").lower() in _SKIPPED_IDS
            or self._skipping()
        )
        if tag in _BLOCKS:
            self._flush()
        if tag in _VOID:
            return
        self._stack.append((tag, skip))
        if skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = int(tag[1])
        elif tag == "li":
            self._list_item = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        while self._stack:
            open_tag, _ = self._stack.pop()
            if open_tag == tag:
                break
        if tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skipping():
            self._current.append(data)

    def text(self) -> str:
        self._flush()
        out: list[str] = []
        for line in self._lines:
            if line.startswith("#") and out and out[-1] != "":
                out.append("")
            out.append(line)
            if line.startswith("#"):
                out.append("")
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"

    def _skipping(self) -> bool:
        return any(skip for _, skip in self._stack)

    def _flush(self) -> None:
        text = _SPACES.sub(" ", _URL.sub("", "".join(self._current))).strip()
        text = _RDF_TYPE.sub("", text).strip()
        self._current = []
        if text and re.search(r"[A-Za-z]{2}", text) and not _is_boilerplate(text):
            if self._heading:
                text = "#" * self._heading + " " + text
            elif self._list_item:
                text = "- " + text
            self._lines.append(text)
        self._heading = None
        self._list_item = False


def _is_boilerplate(text: str) -> bool:
    """A navigation line, a bare term name such as `gr:Offering`, or a line with no prose."""
    folded = text.casefold()
    return (
        folded in _BOILERPLATE
        or folded.startswith(_BOILERPLATE_PREFIXES)
        or bool(_BARE_TERM.fullmatch(text))
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m evals.html_to_text <in.html> <out.md>", file=sys.stderr)
        return 2
    source, target = Path(argv[0]), Path(argv[1])
    html = source.read_text(encoding="utf-8", errors="replace")
    target.write_text(html_to_markdown(html), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
