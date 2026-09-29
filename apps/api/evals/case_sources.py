"""Finds every bake-off case: YAML datasets and folders of paired documents and gold trees.

A dataset folder holds `*.yaml` files, each with a `cases:` list of `TeachCase` entries; a
document case there names its file in `document:`, relative to the YAML file.

A paired folder (the public documents, each public benchmark, the owner's private folder) groups
its files by name: `<name>.<document suffix>` is a document (several suffixes give one case
each), `<name>.<gold suffix>` its gold tree (OWL, SKOS, OBO, CSV/Excel hierarchy, JSON), and
`<name>.expected.yaml` an optional companion with `company:`, `description:`, `tags:`,
`existing:`, `optional:` and optionally a hand-written `expected:` tree that replaces the gold
file's. An Excel file is a gold tree when it reads as one; with no document beside it, its
definitions column becomes the document. A document with no expectations at all is report-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from evals.doc_formats.loader import DOCUMENT_SUFFIXES
from evals.gold.loader import GOLD_SUFFIXES, load_gold
from evals.gold.table_gold import pcf_definitions_text
from evals.teach_case import CaseOrigin, TeachCase, ensure_unique, load_cases

COMPANION_SUFFIX = ".expected.yaml"


@dataclass(frozen=True)
class PairedFolder:
    path: Path
    origin: CaseOrigin


@dataclass
class Discovery:
    cases: list[TeachCase] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def discover(dataset_dirs: list[Path], paired: list[PairedFolder], derived_dir: Path) -> Discovery:
    found = Discovery()
    for folder in dataset_dirs:
        for path in sorted([*folder.glob("*.yaml"), *folder.glob("*.yml")]):
            for case in load_cases(path):
                if case.document is not None and not case.document.is_absolute():
                    case = case.model_copy(update={"document": path.parent / case.document})
                found.cases.append(case)
    for folder in paired:
        if folder.path.is_dir():
            _paired(folder, derived_dir, found)
    ensure_unique(found.cases)
    return found


def benchmark_folders(root: Path) -> list[PairedFolder]:
    return [PairedFolder(p, "benchmarks") for p in sorted(root.iterdir()) if p.is_dir()]


def _paired(folder: PairedFolder, derived_dir: Path, found: Discovery) -> None:
    groups: dict[str, list[Path]] = {}
    for path in sorted(folder.path.iterdir()):
        if not path.is_file() or path.name.lower() == "readme.md":
            continue
        name = path.name
        stem = name[: -len(COMPANION_SUFFIX)] if name.endswith(COMPANION_SUFFIX) else path.stem
        groups.setdefault(stem, []).append(path)
    for stem, paths in groups.items():
        companion = next((p for p in paths if p.name.endswith(COMPANION_SUFFIX)), None)
        rest = [p for p in paths if p is not companion]
        documents = [p for p in rest if p.suffix.lower() in DOCUMENT_SUFFIXES]
        golds = [p for p in rest if p.suffix.lower() in GOLD_SUFFIXES and p not in documents]
        spreadsheets = [p for p in documents if p.suffix.lower() == ".xlsx"]
        # A workbook is first tried as a gold tree when nothing else gives the expectations:
        # beside another document, or alone, and with no hand-written `expected:` companion.
        has_expected = companion is not None and "expected:" in companion.read_text("utf-8")
        for sheet in spreadsheets:
            if not has_expected and (len(documents) > 1 or not golds):
                golds.append(sheet)
                documents.remove(sheet)
        _group(folder, stem, companion, documents, golds, derived_dir, found)


def _group(
    folder: PairedFolder,
    stem: str,
    companion: Path | None,
    documents: list[Path],
    golds: list[Path],
    derived_dir: Path,
    found: Discovery,
) -> None:
    extra = yaml.safe_load(companion.read_text(encoding="utf-8")) if companion else None
    extra = extra or {}
    company = str(extra.get("company") or _humanised(stem))
    expected = extra.get("expected")
    optional = list(extra.get("optional") or [])
    report: dict[str, object] = {}
    gold_path = golds[0] if golds else None
    if len(golds) > 1:
        found.notes.append(f"{folder.path.name}/{stem}: several gold files, using {golds[0].name}")
    if gold_path is not None:
        try:
            gold = load_gold(gold_path, company)
        except Exception as exc:
            found.notes.append(f"{folder.path.name}/{gold_path.name}: not a gold tree ({exc})")
            if gold_path.suffix.lower() == ".xlsx":
                documents.append(gold_path)
            gold = None
        if gold is not None:
            report = {"gold": gold_path.name, **gold.report}
            optional += gold.optional
            if expected is None:
                expected = gold.expected.model_dump(by_alias=True)
            if not documents and gold_path.suffix.lower() in (".xlsx", ".csv"):
                derived = _definitions_document(gold_path, derived_dir)
                if derived is not None:
                    documents.append(derived)
    if not documents:
        found.notes.append(f"{folder.path.name}/{stem}: no document, skipped")
        return
    for document in documents:
        found.cases.append(
            TeachCase.model_validate(
                {
                    "id": _slug(f"{folder.origin}-{folder.path.name}-{document.name}"),
                    "kind": "document",
                    "origin": folder.origin,
                    "company": company,
                    "description": extra.get("description") or f"{document.name}",
                    "tags": list(extra.get("tags") or []) + [folder.origin],
                    "existing": extra.get("existing") or [],
                    "document": document,
                    "expected": expected,
                    "optional": optional,
                    "source_report": report,
                }
            )
        )


def _definitions_document(gold_path: Path, derived_dir: Path) -> Path | None:
    text = pcf_definitions_text(gold_path)
    if not text:
        return None
    derived_dir.mkdir(parents=True, exist_ok=True)
    target = derived_dir / f"{gold_path.stem}.definitions.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def _humanised(stem: str) -> str:
    words = re.split(r"[_\-\s]+", stem)
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or stem


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.") or "case"
