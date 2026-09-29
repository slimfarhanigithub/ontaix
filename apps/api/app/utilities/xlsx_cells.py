"""Cell values of an Excel workbook, row by row, in sheet and row order.

Only cached values are read: a formula is never evaluated, and external links, pivot caches,
images and embedded objects are never opened. A workbook holds at most 50 sheets and 200,000
non-empty cells. Shared strings, inline strings, numbers, dates as stored and booleans are
returned as text; error values are left out.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.ooxml_archive import OoxmlArchive, office_relationship_id

MAX_SHEETS = 50
MAX_CELLS = 200_000

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SHARED_STRINGS_TYPE = "/sharedStrings"
DEFAULT_SHARED_STRINGS = "xl/sharedStrings.xml"

_COLUMN = re.compile(r"^([A-Za-z]{1,3})")


@dataclass(frozen=True)
class SheetRow:
    """One non-empty row: 1-based sheet and row numbers, 0-based column to non-empty value."""

    sheet: int
    row: int
    cells: dict[int, str]


def sheet_rows(
    archive: OoxmlArchive,
    *,
    first_sheet_only: bool = False,
    count_chars: Callable[[int], None] | None = None,
) -> Iterator[SheetRow]:
    """Every non-empty row of the workbook, or of its first sheet only."""
    main = archive.main_part("xlsx")
    if not archive.has(main):
        raise DocumentUnreadableError("the workbook has no sheet list")
    relationships = archive.relationships(main)
    targets = {rid: target for rid, target, _ in relationships}
    shared_part = next(
        (t for _, t, kind in relationships if kind.endswith(SHARED_STRINGS_TYPE)),
        DEFAULT_SHARED_STRINGS,
    )
    sheets = _sheet_parts(archive, main, targets)
    if first_sheet_only:
        sheets = sheets[:1]
    shared = _shared_strings(archive, shared_part) if archive.has(shared_part) else []
    cells = 0
    for number, part in enumerate(sheets, start=1):
        if part is None or not archive.has(part):
            continue
        for row in _rows(archive, part, number, shared):
            cells += len(row.cells)
            if cells > MAX_CELLS:
                raise DocumentTooLargeError(f"more than {MAX_CELLS} non-empty cells")
            if count_chars:
                count_chars(sum(len(v) for v in row.cells.values()))
            yield row


def column_index(reference: str | None) -> int | None:
    """The 0-based column of a cell reference such as `B7`."""
    match = _COLUMN.match(reference or "")
    if not match:
        return None
    index = 0
    for letter in match.group(1).upper():
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def _sheet_parts(archive: OoxmlArchive, main: str, targets: dict[str, str]) -> list[str | None]:
    parts: list[str | None] = []
    for event, element in archive.iterparse(main):
        if event == "end" and element.tag == f"{SHEET_NS}sheet":
            parts.append(targets.get(office_relationship_id(element) or ""))
            if len(parts) > MAX_SHEETS:
                raise DocumentTooLargeError(f"more than {MAX_SHEETS} sheets")
    return parts


def _shared_strings(archive: OoxmlArchive, part: str) -> list[str]:
    """The shared string table; phonetic runs are left out."""
    strings: list[str] = []
    current: list[str] = []
    phonetic = 0
    for event, element in archive.iterparse(part):
        tag = element.tag
        if event == "start":
            if tag == f"{SHEET_NS}si":
                current = []
            elif tag == f"{SHEET_NS}rPh":
                phonetic += 1
            continue
        if tag == f"{SHEET_NS}rPh":
            phonetic -= 1
        elif tag == f"{SHEET_NS}t" and not phonetic and element.text:
            current.append(element.text)
        elif tag == f"{SHEET_NS}si":
            strings.append("".join(current))
    return strings


def _rows(archive: OoxmlArchive, part: str, sheet: int, shared: list[str]) -> Iterator[SheetRow]:
    row_number = 0
    cells: dict[int, str] = {}
    cell_type: str | None = None
    cell_column = 0
    value: list[str] = []
    inline: list[str] = []
    for event, element in archive.iterparse(part):
        tag = element.tag
        if event == "start":
            if tag == f"{SHEET_NS}row":
                declared = element.get("r")
                row_number = int(declared) if declared and declared.isdigit() else row_number + 1
                cells = {}
                cell_column = -1
            elif tag == f"{SHEET_NS}c":
                cell_type = element.get("t")
                found = column_index(element.get("r"))
                cell_column = found if found is not None else cell_column + 1
                value, inline = [], []
            continue
        if tag == f"{SHEET_NS}v" and element.text:
            value.append(element.text)
        elif tag == f"{SHEET_NS}t" and element.text:
            inline.append(element.text)
        elif tag == f"{SHEET_NS}c":
            text = _cell_text(cell_type, "".join(value), "".join(inline), shared).strip()
            if text:
                cells[cell_column] = text
        elif tag == f"{SHEET_NS}row" and cells:
            yield SheetRow(sheet, row_number, cells)
            cells = {}


def _cell_text(cell_type: str | None, value: str, inline: str, shared: list[str]) -> str:
    if cell_type == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ""
    if cell_type == "inlineStr":
        return inline
    if cell_type == "b":
        return "TRUE" if value.strip() == "1" else "FALSE"
    if cell_type == "e":
        return ""
    return value
