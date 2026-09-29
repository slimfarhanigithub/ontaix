"""Small Office documents built in memory for tests: PPTX decks and XLSX workbooks.

Each is the least an Office reader needs - content types, the main part, its relationships and
the slide, notes, sheet and shared-string parts - so tests hold no binary fixtures.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PPTX_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
PPTM_MAIN = "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"
XLSX_MAIN = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def content_types(overrides: dict[str, str]) -> str:
    entries = "".join(
        f'<Override PartName="/{part}" ContentType="{kind}"/>' for part, kind in overrides.items()
    )
    return f'<Types xmlns="{CT_NS}">{entries}</Types>'


def relationships(targets: list[tuple[str, str, str]]) -> str:
    entries = "".join(
        f'<Relationship Id="{rid}" Type="{OFFICE_REL}/{kind}" Target="{target}"/>'
        for rid, kind, target in targets
    )
    return f'<Relationships xmlns="{REL_NS}">{entries}</Relationships>'


def zipped(parts: dict[str, str | bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return out.getvalue()


def pptx(
    slides: list[tuple[list[str], list[str]]],
    main_type: str = PPTX_MAIN,
    extra: dict[str, str | bytes] | None = None,
) -> bytes:
    """A deck whose slides hold paragraphs of text and speaker notes: `(texts, notes)` each."""
    parts: dict[str, str | bytes] = {}
    overrides = {"ppt/presentation.xml": main_type}
    ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(len(slides)))
    parts["ppt/presentation.xml"] = (
        f'<p:presentation xmlns:p="{P_NS}" xmlns:r="{OFFICE_REL}">'
        f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>"
    )
    parts["ppt/_rels/presentation.xml.rels"] = relationships(
        [(f"rId{i + 1}", "slide", f"slides/slide{i + 1}.xml") for i in range(len(slides))]
    )
    for i, (texts, notes) in enumerate(slides, start=1):
        parts[f"ppt/slides/slide{i}.xml"] = _drawing("p:sld", texts)
        overrides[f"ppt/slides/slide{i}.xml"] = (
            "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
        )
        if notes:
            parts[f"ppt/notesSlides/notesSlide{i}.xml"] = _drawing("p:notes", notes)
            parts[f"ppt/slides/_rels/slide{i}.xml.rels"] = relationships(
                [("rId1", "notesSlide", f"../notesSlides/notesSlide{i}.xml")]
            )
    parts.update(extra or {})
    return zipped({"[Content_Types].xml": content_types(overrides), **parts})


def xlsx(
    sheets: list[list[list[str | int | None]]],
    formula_cells: dict[str, tuple[str, str]] | None = None,
) -> bytes:
    """A workbook of sheets of rows; strings go to the shared string table, numbers inline.
    `formula_cells` maps a cell reference of the first sheet to `(formula, cached value)`."""
    shared: list[str] = []
    parts: dict[str, str | bytes] = {}
    overrides = {"xl/workbook.xml": XLSX_MAIN}
    sheet_entries = "".join(
        f'<sheet name="S{i}" sheetId="{i}" r:id="rId{i}"/>' for i in range(1, len(sheets) + 1)
    )
    parts["xl/workbook.xml"] = (
        f'<workbook xmlns="{S_NS}" xmlns:r="{OFFICE_REL}">'
        f"<sheets>{sheet_entries}</sheets></workbook>"
    )
    targets = [
        (f"rId{i}", "worksheet", f"worksheets/sheet{i}.xml") for i in range(1, len(sheets) + 1)
    ]
    targets.append(("rIdS", "sharedStrings", "sharedStrings.xml"))
    parts["xl/_rels/workbook.xml.rels"] = relationships(targets)
    for number, rows in enumerate(sheets, start=1):
        body = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, value in enumerate(row):
                ref = f"{chr(ord('A') + c)}{r}"
                if number == 1 and formula_cells and ref in formula_cells:
                    formula, cached = formula_cells[ref]
                    cells.append(
                        f'<c r="{ref}" t="str"><f>{escape(formula)}</f><v>{escape(cached)}</v></c>'
                    )
                elif isinstance(value, int):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                elif value:
                    shared.append(value)
                    cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        parts[f"xl/worksheets/sheet{number}.xml"] = (
            f'<worksheet xmlns="{S_NS}"><sheetData>{"".join(body)}</sheetData></worksheet>'
        )
    strings = "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
    parts["xl/sharedStrings.xml"] = f'<sst xmlns="{S_NS}">{strings}</sst>'
    return zipped({"[Content_Types].xml": content_types(overrides), **parts})


def _drawing(root: str, texts: list[str]) -> str:
    paragraphs = "".join(f"<a:p><a:r><a:t>{escape(t)}</a:t></a:r></a:p>" for t in texts)
    return (
        f'<{root} xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree><p:sp><p:txBody>'
        f"{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld></{root}>"
    )
