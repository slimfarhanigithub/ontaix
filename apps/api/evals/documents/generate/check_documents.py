"""Checks every full bake-off document against its hand-written gold tree.

For each `<name>.expected.yaml` in `evals/documents/` with a `<name>.md` next to it:

- the gold loads (company, expected concepts and relations, optional labels);
- no two expected labels (or aliases) name the same concept after the scorer's normalisation;
- every parent is the company root or another expected concept, and the tree has no cycle;
- the tree has at least `--min-nodes` concepts and reaches `--min-depth` levels;
- every expected label and alias is grounded: it occurs as whole words (case folded, last word
  singular or plural) in a sentence the import keeps, split exactly as the import splits Markdown
  (whitespace collapsed, split after `.`, `!` or `?`, sentences of 13 to 399 characters);
- every relation joins two expected concepts (or the root);
- the Markdown holds no sentence the import would drop for being over 399 characters;
- for each expected concept, its label and one of its parents occur in the same sentence or
  within two sentences of each other (the context the document mode gives the model); a miss is
  reported as a warning, since a heading can carry the parent further away;
- for documents tagged `adversarial` (checked against at least 20 concepts and 3 levels), every
  label listed in `source_report.injected` occurs in the document and is neither expected nor
  optional.

Documents tagged `document-structure` are written like real business documents (headings with no
full stop, bullet and numbered lists, table rows, sentences over 399 characters, line breaks
inside paragraphs) and are the regression cases of the import split. For them, labels are
grounded against lines and sentences of the file as written, long sentences are required rather
than refused, at least 40 concepts are required, each layout feature must occur at least three
times, and at least one gold label must be lost by the current collapse-then-split import.

Needs PyYAML only. Run: `python check_documents.py [--documents DIR]`. Exits 1 on any error.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

MIN_SENTENCE_CHARS = 13
MAX_SENTENCE_CHARS = 399
CONTEXT_WINDOW = 2
# Documents written like real business documents, the regression cases of the import split.
STRUCTURE_TAG = "document-structure"
STRUCTURE_MIN_NODES = 40
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"\w+")
_LEADING = frozenset({"the", "a", "an", "our", "its", "their", "each", "every", "all"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--min-nodes", type=int, default=80)
    parser.add_argument("--min-depth", type=int, default=4)
    args = parser.parse_args()
    failures = 0
    for gold_path in sorted(args.documents.glob("*.expected.yaml")):
        name = gold_path.name.removesuffix(".expected.yaml")
        md = args.documents / f"{name}.md"
        if not md.exists():
            print(f"{name}: no {md.name}")
            failures += 1
            continue
        errors, warnings, stats = check(gold_path, md, args.min_nodes, args.min_depth)
        status = "OK" if not errors else "FAIL"
        print(f"{status} {name}: {stats}")
        for e in errors:
            print(f"  ERROR {e}")
        for w in warnings:
            print(f"  warn  {w}")
        failures += bool(errors)
    return 1 if failures else 0


def check(
    gold_path: Path, md_path: Path, min_nodes: int, min_depth: int
) -> tuple[list[str], list[str], str]:
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    company = gold["company"]
    root = normalise_label(company)
    concepts = gold["expected"]["concepts"]
    relations = gold["expected"].get("relations", [])
    tags = gold.get("tags", [])
    if "adversarial" in tags:
        min_nodes, min_depth = min(min_nodes, 20), min(min_depth, 3)
    structure = STRUCTURE_TAG in tags
    if structure:
        min_nodes = min(min_nodes, STRUCTURE_MIN_NODES)

    text = md_path.read_text(encoding="utf-8")
    all_parts = [p.strip() for p in _SPLIT.split(re.sub(r"\s+", " ", text))]
    kept = [p for p in all_parts if MIN_SENTENCE_CHARS <= len(p) <= MAX_SENTENCE_CHARS]
    kept_words = [[singular(w) for w in words(s)] for s in kept]
    if structure:
        # Grounded against the document's own units (lines, then sentences), as a splitter that
        # keeps line breaks and long sentences reads it.
        sentences = [
            s.strip()
            for line in text.splitlines()
            for s in re.split(r"(?<=[.!?])\s+", line)
            if s.strip()
        ]
        errors += structure_problems(text, all_parts)
    else:
        for p in all_parts:
            if len(p) > MAX_SENTENCE_CHARS:
                errors.append(f"sentence over {MAX_SENTENCE_CHARS} chars is dropped: {p[:80]}...")
        sentences = kept
    sentence_words = [[singular(w) for w in words(s)] for s in sentences]
    lost_today = [
        c["label"]
        for c in concepts
        if not any(grounded_in(label, kept_words) for label in [c["label"], *c.get("aliases", [])])
    ]
    if structure and not lost_today:
        errors.append("a structure regression document loses no gold label to the current split")

    names: dict[str, str] = {}
    parents: dict[str, list[str]] = {}
    for c in concepts:
        labels = [c["label"], *c.get("aliases", [])]
        for label in labels:
            n = normalise_label(label)
            if n in names and names[n] != c["label"]:
                errors.append(f"'{label}' collides with '{names[n]}'")
            if n == root:
                errors.append(f"'{label}' names the company root")
            names[n] = c["label"]
        key = normalise_label(c["label"])
        if key in parents:
            errors.append(f"'{c['label']}' is listed twice")
        parents[key] = [normalise_label(p) for p in as_list(c["parent"])]
        if not as_list(c.get("action")):
            errors.append(f"'{c['label']}' has no action")
        if not any(grounded_in(label, sentence_words) for label in labels):
            errors.append(f"'{c['label']}' is not grounded in the document")
        for alias in c.get("aliases", []):
            if not grounded_in(alias, sentence_words):
                warnings.append(f"alias '{alias}' of '{c['label']}' is not in the document")
    for key, ps in parents.items():
        for p in ps:
            if p != root and p not in parents:
                errors.append(f"parent '{p}' of '{names[key]}' is neither the root nor expected")

    depth: dict[str, int] = {}

    def level(n: str, seen: frozenset[str] = frozenset()) -> int:
        if n == root:
            return 0
        if n in depth:
            return depth[n]
        if n in seen:
            errors.append(f"cycle through '{names.get(n, n)}'")
            return 10**6
        ups = [p for p in parents.get(n, []) if p == root or p in parents]
        best = min((level(p, seen | {n}) for p in ups), default=0)
        depth[n] = best + 1
        return depth[n]

    levels = [level(n) for n in parents]
    max_depth = max(levels, default=0)
    if len(parents) < min_nodes:
        errors.append(f"{len(parents)} concepts, fewer than {min_nodes}")
    if max_depth < min_depth:
        errors.append(f"depth {max_depth}, less than {min_depth}")

    for r in relations:
        for end in (r["from"], r["to"]):
            n = normalise_label(end)
            if n != root and n not in names:
                errors.append(f"relation end '{end}' is not an expected concept")
        if not as_list(r.get("action")):
            errors.append(f"relation {r['from']} -> {r['to']} has no action")

    for c in concepts:
        child = [singular(w) for w in words(c["label"])]
        hits = [i for i, sw in enumerate(sentence_words) if contains(sw, child)]
        near = False
        for p in as_list(c["parent"]):
            if normalise_label(p) == root:
                near = True
                break
            parent_words = [singular(w) for w in words(p)]
            for i in hits:
                lo, hi = max(0, i - CONTEXT_WINDOW), i + CONTEXT_WINDOW + 1
                if any(contains(sw, parent_words) for sw in sentence_words[lo:hi]):
                    near = True
                    break
            if near:
                break
        if not near:
            warnings.append(f"'{c['label']}' never appears near its parent {c['parent']}")

    optional = [normalise_label(o) for o in gold.get("optional", [])]
    if "adversarial" in tags:
        injected_labels = gold.get("source_report", {}).get("injected", [])
        if not injected_labels:
            errors.append("adversarial document lists no source_report.injected labels")
        for injected in injected_labels:
            n = normalise_label(injected)
            if n in names or n in optional:
                errors.append(f"injected label '{injected}' is expected or optional")
            if not grounded_in(injected, sentence_words):
                errors.append(f"injected label '{injected}' does not occur in the document")

    per_level = {}
    for lv in levels:
        per_level[lv] = per_level.get(lv, 0) + 1
    stats = (
        f"{len(parents)} concepts, depth {max_depth}, levels {dict(sorted(per_level.items()))}, "
        f"{len(relations)} relations, {len(sentences)} sentences, "
        f"{len(words(text))} words"
    )
    if structure:
        stats += f", {len(lost_today)} gold labels lost to the current import split"
    return errors, warnings, stats


def structure_problems(text: str, collapsed_parts: list[str]) -> list[str]:
    """What a structure regression document lacks of real document layout."""
    lines = text.splitlines()
    headings = [x for x in lines if re.match(r"#{1,4}\s", x) and not x.rstrip().endswith(".")]
    bullets = [x for x in lines if re.match(r"\s*[-*]\s", x)]
    numbered = [x for x in lines if re.match(r"\s*\d+[.)]\s", x)]
    rows = [x for x in lines if x.lstrip().startswith("|")]
    long_sentences = [p for p in collapsed_parts if len(p) > MAX_SENTENCE_CHARS]
    wrapped = [
        block
        for block in re.split(r"\n\s*\n", text)
        if len(block.splitlines()) > 1
        and not re.match(r"\s*([-*|#]|\d+[.)])", block)
    ]
    wanted = {
        "headings without a full stop": (len(headings), 3),
        "bullet items": (len(bullets), 3),
        "numbered items": (len(numbered), 3),
        "table rows": (len(rows), 3),
        f"sentences over {MAX_SENTENCE_CHARS} characters after the import collapse": (
            len(long_sentences),
            3,
        ),
        "paragraphs with line breaks inside": (len(wrapped), 3),
    }
    return [f"only {n} {what}, want {m}" for what, (n, m) in wanted.items() if n < m]


def as_list(value: object) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    return _WORD.findall(folded.replace("_", " "))


def singular(w: str) -> str:
    w = re.sub(r"ies$", "y", w, count=1)
    w = re.sub(r"(ch|sh|s|x|z)es$", r"\1", w, count=1)
    return re.sub(r"([^s])s$", r"\1", w, count=1)


def normalise_label(label: str) -> str:
    ws = words(label)
    while len(ws) > 1 and ws[0] in _LEADING:
        ws = ws[1:]
    if ws:
        ws[-1] = singular(ws[-1])
    return " ".join(ws)


def contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def grounded_in(label: str, sentence_words: list[list[str]]) -> bool:
    wanted = [singular(w) for w in words(label)]
    return any(contains(sw, wanted) for sw in sentence_words)


if __name__ == "__main__":
    sys.exit(main())
