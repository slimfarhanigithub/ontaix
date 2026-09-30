"""CSV and XLSX hierarchies read as items, in file order.

The first non-empty row is the header, matched without regard to case or surrounding space.
With `label` and `parent` columns (optional `id`, `action`, `domain`), each row with a label is
one item under the row its `parent` names by `id`, else by `label`; an empty parent is the top.
With level columns `Level 1`, `Level 2` and so on, each non-empty cell is one item under the
nearest cell to its left, carried down from earlier rows when this row leaves it empty; a
repeated path is one item. A row's source is `row <n>`, its 1-based line or sheet row. At most
200,000 rows. `is_csv_hierarchy` and `is_xlsx_hierarchy` read the header row alone, to tell a
hierarchy table from a document table.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Iterator

from app.models.ontology_import.parsed_ontology import (
    RDFS_LABEL,
    LabelLiteral,
    OntologyFormat,
    OntologyItem,
    ParsedOntology,
    SkippedSource,
)
from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.document_text import decode_text
from app.utilities.ooxml_archive import OoxmlArchive
from app.utilities.xlsx_cells import sheet_rows

MAX_ROWS = 200_000
_LEVEL = re.compile(r"^level\s*(\d+)$")

Row = tuple[int, dict[int, str]]


def read_csv_hierarchy(data: bytes) -> ParsedOntology:
    return _read(_csv_rows(decode_text(data)), "csv")


def read_xlsx_hierarchy(data: bytes) -> ParsedOntology:
    with OoxmlArchive(data, "the workbook") as archive:
        rows = [(r.row, r.cells) for r in sheet_rows(archive, first_sheet_only=True)]
    return _read(rows, "xlsx")


def is_csv_hierarchy(data: bytes) -> bool:
    """True when the first non-empty row of the CSV text is a hierarchy header; False when the
    text is not UTF-8 or its first rows are not well-formed CSV."""
    try:
        text = decode_text(data)
        header = next((cells for _, cells in _csv_rows(text) if cells), None)
    except (UnicodeDecodeError, csv.Error):
        return False
    return header is not None and _is_header(header)


def is_xlsx_hierarchy(data: bytes) -> bool:
    """True when the first non-empty row of the workbook's first sheet is a hierarchy header."""
    with OoxmlArchive(data, "the workbook") as archive:
        header = next(
            (r.cells for r in sheet_rows(archive, first_sheet_only=True) if r.cells), None
        )
    return header is not None and _is_header(header)


def _csv_rows(text: str) -> Iterator[Row]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return (
        (number, {i: c.strip() for i, c in enumerate(cells) if c.strip()})
        for number, cells in enumerate(csv.reader(io.StringIO(text), dialect), start=1)
    )


def _is_header(cells: dict[int, str]) -> bool:
    """Label and parent columns, or at least one `Level <n>` column."""
    names = {name.strip().lower() for name in cells.values()}
    return {"label", "parent"} <= names or any(_LEVEL.match(name) for name in names)


def _read(rows: Iterable[Row], fmt: OntologyFormat) -> ParsedOntology:
    counted = _counted(r for r in rows if r[1])
    header = next(counted, None)
    if header is None:
        raise DocumentUnreadableError("the hierarchy has no header row")
    columns = {name.lower(): i for i, name in header[1].items()}
    levels = sorted(
        (int(m.group(1)), i) for name, i in columns.items() if (m := _LEVEL.match(name))
    )
    parsed = ParsedOntology(format=fmt, table=True)
    if "label" in columns and "parent" in columns:
        _parent_rows(parsed, counted, columns)
    elif levels:
        _level_rows(parsed, counted, [i for _, i in levels])
    else:
        raise DocumentUnreadableError(
            "the hierarchy needs label and parent columns, or Level 1, Level 2 and so on"
        )
    return parsed


def _counted(rows: Iterable[Row]) -> Iterator[Row]:
    for count, row in enumerate(rows, start=1):
        if count > MAX_ROWS + 1:
            raise DocumentTooLargeError(f"more than {MAX_ROWS} rows")
        yield row


def _parent_rows(parsed: ParsedOntology, rows: Iterator[Row], columns: dict[str, int]) -> None:
    entries: list[tuple[OntologyItem, str]] = []
    by_id: dict[str, str] = {}
    by_label: dict[str, str] = {}
    for number, cells in rows:
        label = cells.get(columns["label"], "")
        if not label:
            continue
        source = f"row {number}"
        item = OntologyItem(source=source, local_name=label)
        item.add_label(RDFS_LABEL, LabelLiteral(label))
        if "action" in columns:
            item.action = cells.get(columns["action"]) or None
        if "domain" in columns:
            item.domain = cells.get(columns["domain"]) or None
        if "id" in columns and cells.get(columns["id"]):
            by_id.setdefault(cells[columns["id"]], source)
        by_label.setdefault(label.lower(), source)
        entries.append((item, cells.get(columns["parent"], "")))
    # A row's parent row, or None at the top; a parent naming no other row makes it unknown.
    parent_of: dict[str, str | None] = {}
    unknown: set[str] = set()
    for item, parent in entries:
        found = (by_id.get(parent) or by_label.get(parent.lower())) if parent else None
        if parent and (found is None or found == item.source):
            unknown.add(item.source)
        parent_of[item.source] = found
    changed = True
    while changed:
        changed = False
        for source, found in parent_of.items():
            if source not in unknown and found and found in unknown:
                unknown.add(source)
                changed = True
    for item, _ in entries:
        if item.source in unknown:
            parsed.skipped.append(SkippedSource(item.source, "unknown_parent"))
            continue
        found = parent_of[item.source]
        if found:
            item.parents.append((found, "includes"))
        parsed.items.append(item)


def _level_rows(parsed: ParsedOntology, rows: Iterator[Row], level_columns: list[int]) -> None:
    by_path: dict[tuple[str, ...], str] = {}
    carried: list[tuple[str, ...] | None] = [None] * len(level_columns)
    for number, cells in rows:
        new_in_row = 0
        for depth, column in enumerate(level_columns):
            label = cells.get(column, "")
            if not label:
                continue
            parent_path = carried[depth - 1] if depth > 0 else ()
            if parent_path is None:
                parsed.skipped.append(SkippedSource(f"row {number}", "unknown_parent"))
                continue
            path = (*parent_path, label.lower())
            carried[depth] = path
            for deeper in range(depth + 1, len(level_columns)):
                carried[deeper] = None
            if path in by_path:
                continue
            new_in_row += 1
            # A row holding several new cells names the second and later by their level.
            source = f"row {number}" if new_in_row == 1 else f"row {number} level {depth + 1}"
            item = OntologyItem(source=source, local_name=label)
            item.add_label(RDFS_LABEL, LabelLiteral(label))
            if parent_path:
                item.parents.append((by_path[parent_path], "includes"))
            by_path[path] = source
            parsed.items.append(item)
