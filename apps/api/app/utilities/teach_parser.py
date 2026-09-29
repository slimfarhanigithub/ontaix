"""Rule-based teach parser: subject, action, object; "A is a B"; "A that ... is a B"; lists;
passives; an "In <domain>, ..." prefix.

The same grammar the Studio's reference runs (`STOP`, `title`, `DET`, `VERBS_LEX`, `CANON`,
`VERB_RE`, `singular`, `cleanNP`, `splitList`, `understand`, the domain prefix), rule for rule,
so a sentence reads the same whether it is typed, spoken or imported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STOP = frozenset(
    (
        "a an the and or of to in on at for with by from we our your their my is are was were be "
        "been it its this that these those who which what how many much some any all every each "
        "new old have has had do does did make makes use uses also very more most less than into "
        "over under about through there here when where then them they you he she his her run runs"
    ).split(" ")
)

DET = re.compile(
    r"^(?:a|an|the|each|every|all|our|its|their|some|many|any|one|this|that|these|those|of|new)\s+"
)

VERBS_LEX = (
    "is a kind of", "is a type of", "is part of", "is made of", "is made from", "consists of",
    "is composed of", "is executed on", "is executed by", "is placed by", "is bought from",
    "is sold to", "is stored in", "is produced by", "is produced in", "is checked by",
    "is inspected by", "is monitored by", "is handled by", "is managed by", "is owned by",
    "is defined by", "is validated by", "is scheduled by", "is staffed by", "is billed by",
    "is charged to", "is fulfilled by", "is delivered by", "is shipped as", "is grouped in",
    "is limited by", "is priced from", "is earned through", "is governed by", "is followed by",
    "is preceded by", "belongs to", "reports to", "depends on", "delivers to", "sells to",
    "buys from", "leads to", "results in", "applies to", "refers to", "runs in", "runs on",
    "works in", "works on", "operates", "manages", "owns", "produces", "makes", "builds",
    "creates", "generates", "uses", "consumes", "needs", "requires", "contains", "includes",
    "has", "have", "holds", "runs", "executes", "places", "receives", "sends", "ships",
    "delivers", "stores", "tracks", "records", "monitors", "measures", "checks", "inspects",
    "validates", "tests", "triggers", "starts", "schedules", "plans", "assigns", "employs",
    "trains", "certifies", "serves", "supplies", "provides", "feeds", "defines", "specifies",
    "updates", "evolves", "issues", "pays", "invoices", "bills", "approves", "raises", "handles",
    "follows", "precedes", "supports", "maintains", "repairs", "replaces", "installs", "packs",
    "loads", "routes", "processes", "transforms", "assembles", "welds", "paints", "moves",
    "carries", "transports", "fulfils", "fulfills", "covers", "governs", "groups", "limits",
    "prices", "signs", "opens", "closes",
)  # fmt: skip


def _canon_and_variants() -> tuple[dict[str, str], list[str]]:
    canon: dict[str, str] = {}
    variants: list[str] = []
    for v in VERBS_LEX:
        canon[v] = v
        variants.append(v)
        if v.startswith("is "):
            a = "are " + v[3:]
            canon[a] = v
            variants.append(a)
        elif not re.search(r"\s", v):
            b: str | None = None
            if v == "has":
                b = "have"
            elif v.endswith("ies"):
                b = v[:-3] + "y"
            elif re.search(r"(ch|sh|ss|x|z)es$", v):
                b = v[:-2]
            elif v.endswith("s"):
                b = v[:-1]
            if b and len(b) > 2:
                canon[b] = v
                variants.append(b)
    return canon, variants


CANON, _VARIANTS = _canon_and_variants()

VERB_RE = re.compile(
    r"\b("
    + "|".join(re.sub(r"\s+", r"\\s+", v) for v in sorted(_VARIANTS, key=len, reverse=True))
    + r")\b"
)

DOMAIN_PREFIX = re.compile(
    r"^in (production|supply chain|supply|sales|logistics|quality|maintenance|finance|people|hr"
    r"|engineering)[,:]?\s*"
)

_SPEC_WITH_RULE = re.compile(
    r"^(.+?)\s+(?:that|who|which)\s+(.+?)\s+(?:is|are)\s+(?:a |an |the )?(.+)$"
)
_SPEC = re.compile(r"^(.+?)\s+(?:is|are)\s+(?:a |an )?(?:kind of |type of |sort of )?(.+)$")
_SPEC_PREPOSITION = re.compile(r"\s(?:by|in|on|to|of|from|with)\s")
_CLAUSE_SPLIT = re.compile(
    r"\s*[;]\s*|\s*,\s*(?:and\s+)?(?=(?:a|an|the|each|every|all|our|its|their)\s)"
    r"|\s+and\s+(?=(?:a|an|the|each|every|all|our|its|their)\s)"
)
_PREPOSITIONAL = re.compile(r"^(.*?)\s+(to|into|from|in|on|at|with|through|for)\s+(.+)$")


@dataclass(frozen=True)
class ParsedIntent:
    kind: str
    subj: str
    obj: str
    pred: str | None = None
    rule: str | None = None


def title(s: str) -> str:
    return s[:1].upper() + s[1:]


def singular(w: str) -> str:
    w = re.sub(r"ies$", "y", w, count=1)
    w = re.sub(r"(ch|sh|s|x|z)es$", r"\1", w, count=1)
    return re.sub(r"([^s])s$", r"\1", w, count=1)


def clean_np(np: str) -> str:
    np = re.sub(r"^[,;:\s]+", "", re.sub(r"[.!?,;:]+$", "", np.strip()), count=1)
    guard = 0
    while DET.search(np) and guard < 4:
        guard += 1
        np = DET.sub("", np, count=1)
    w = [x for x in re.split(r"\s+", np) if x]
    if not w:
        return ""
    w[-1] = singular(w[-1])
    return " ".join(w)


def split_list(np: str) -> list[str]:
    return [x for x in (clean_np(p) for p in re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", np)) if x]


def understand(text: str) -> list[ParsedIntent]:
    """The intents of one sentence."""
    lower = re.sub(r"[.!?]+$", "", re.sub(r"\s+", " ", text.lower().strip()))
    out: list[ParsedIntent] = []
    m = _SPEC_WITH_RULE.match(lower)
    if m:
        out.append(ParsedIntent("spec", subj=clean_np(m[3]), rule=m[2].strip(), obj=clean_np(m[1])))
        return out
    m = _SPEC.match(lower)
    if m and not VERB_RE.search(m[2]) and not _SPEC_PREPOSITION.search(m[2]):
        out.append(ParsedIntent("spec", subj=clean_np(m[1]), obj=clean_np(m[2])))
        return out
    for cl in _CLAUSE_SPLIT.split(lower):
        v = None
        for mm in VERB_RE.finditer(cl):
            if clean_np(cl[: mm.start()]):
                v = mm
                break
        if v is None:
            continue
        subj = clean_np(cl[: v.start()])
        pred = CANON.get(re.sub(r"\s+", " ", v[1])) or v[1]
        rest = cl[v.end() :]
        if not subj:
            continue
        pp = _PREPOSITIONAL.match(rest)
        if pp and clean_np(pp[1]):
            rest = pp[1]
            for obj in split_list(pp[3]):
                out.append(ParsedIntent("rel", subj=subj, pred=f"{pred} {pp[2]}", obj=obj))
        for obj in split_list(rest):
            out.append(ParsedIntent("rel", subj=subj, pred=pred, obj=obj))
    return out


def domain_prefix(text: str) -> tuple[str | None, str]:
    """Strips an "In <domain>, " prefix; returns the domain key and the remaining text."""
    dm = DOMAIN_PREFIX.match(text.lower())
    if not dm:
        return None, text
    name = dm[1]
    key = "supply" if name.startswith("supply") else "people" if name == "hr" else name
    return key, text[len(dm[0]) :]


def content_words(text: str) -> list[str]:
    """Words of a sentence that can name a concept, for the fallback."""
    words = re.split(r"\s+", re.sub(r"[^a-z\s-]", " ", text.lower()))
    return [singular(w) for w in words if len(w) > 3 and w not in STOP]
