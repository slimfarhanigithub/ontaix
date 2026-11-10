"""Rule-based teach parser: subject, action, object; "A is a B"; "A that ... is a B"; lists;
passives; an "In <domain>, ..." prefix.

The same grammar the Studio's reference runs (`STOP`, `title`, `DET`, `VERBS_LEX`, `CANON`,
`VERB_RE`, `singular`, `cleanNP`, `splitList`, `understand`, the domain prefix), rule for rule,
so a sentence reads the same whether it is typed, spoken or imported.

Every entry point takes the company's language. English is the reference grammar, unchanged.
French and German have their own determiners, stop words, verb lexicons (each verb with its
plural, a passive with its agreements), "est un", "est un type de", "ist ein", "ist eine Art
von" as specialisations, "qui", "die" and "der" relative clauses as rules, "et", "ou", "und",
"oder" and "sowie" as list separators, and their own plural rules (`-s`, `-x`, `-aux` in
French; `-en`, `-e`, `-n`, `-innen` and the vowel-changing plurals in German). A French or
German sentence keeps its casing, so a German noun keeps its capital inside a label; the
English grammar lowercases as the reference does.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.utilities.language import Language

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

# French verbs the grammar reads, in the third person singular; the plural, and for a passive
# the feminine and plural agreements, are generated. A verb's canonical action is the singular.
VERBS_LEX_FR = (
    "est un type de", "est une sorte de", "fait partie de", "est composé de", "se compose de",
    "est constitué de", "se divise en", "est divisé en", "est réparti en", "est géré par",
    "est piloté par", "est produit par", "est fabriqué par", "est vendu à", "est acheté auprès de",
    "est stocké dans", "est contrôlé par", "est suivi par", "est livré par", "est facturé à",
    "est défini par", "est validé par", "est planifié par", "est précédé de", "est suivi de",
    "est lié à", "est rattaché à", "appartient à", "dépend de", "rend compte à", "livre à",
    "vend à", "achète auprès de", "achète à", "mène à", "conduit à", "aboutit à", "s'applique à",
    "fait référence à", "relève de", "se trouve dans", "travaille sur", "travaille dans",
    "travaille avec", "collabore avec", "s'appuie sur", "repose sur", "participe à",
    "contribue à", "porte sur", "passe par", "commence par", "se termine par", "exploite",
    "gère", "pilote", "possède", "détient", "produit", "fabrique", "construit", "crée", "génère",
    "utilise", "consomme", "nécessite", "requiert", "contient", "comprend", "inclut", "comporte",
    "a", "regroupe", "rassemble", "exécute", "effectue", "réalise", "passe", "reçoit", "envoie",
    "expédie", "livre", "stocke", "suit", "enregistre", "trace", "surveille", "mesure",
    "vérifie", "contrôle", "inspecte", "valide", "teste", "déclenche", "lance", "démarre",
    "planifie", "organise", "attribue", "emploie", "forme", "certifie", "sert", "fournit",
    "alimente", "définit", "précise", "met à jour", "émet", "paie", "facture", "approuve",
    "traite", "précède", "supporte", "soutient", "maintient", "répare", "remplace", "installe",
    "emballe", "charge", "achemine", "transforme", "assemble", "soude", "peint", "déplace",
    "transporte", "couvre", "régit", "limite", "signe", "ouvre", "ferme", "dirige", "supervise",
    "coordonne", "distribue", "propose", "offre", "commercialise", "développe", "conçoit",
    "accompagne", "héberge", "opère", "consolide", "déclare", "élabore", "prépare", "garantit",
    "collecte", "assure", "attend", "exige", "centralise", "délivre", "anime", "vise",
    "concerne", "déclenche", "intervient sur", "intervient dans",
)  # fmt: skip

# German verbs the grammar reads, in the third person singular; the plural is generated.
VERBS_LEX_DE = (
    "ist eine art von", "ist eine art", "ist teil von", "besteht aus", "setzt sich zusammen aus",
    "gliedert sich in", "teilt sich in", "ist unterteilt in", "ist aufgeteilt in",
    "wird verwaltet von", "wird geleitet von", "wird produziert von", "wird hergestellt von",
    "wird geliefert von", "wird verkauft an", "wird gekauft von", "wird gelagert in",
    "wird geprüft von", "wird kontrolliert von", "wird betreut von", "wird bearbeitet von",
    "wird definiert durch", "wird ausgeführt von", "wird ausgeführt auf", "wird fakturiert an",
    "wird gefolgt von", "ist verbunden mit", "ist verknüpft mit", "ist zuständig für",
    "ist verantwortlich für", "gehört zu", "berichtet an", "hängt ab von", "liefert an",
    "verkauft an", "kauft von", "kauft bei", "führt zu", "resultiert in", "gilt für",
    "bezieht sich auf", "läuft auf", "läuft in", "arbeitet in", "arbeitet an", "arbeitet mit",
    "kümmert sich um", "verfügt über", "beginnt mit", "endet mit", "folgt auf", "umfasst",
    "enthält", "beinhaltet", "hat", "besitzt", "betreibt", "verwaltet", "leitet", "steuert",
    "führt", "produziert", "fertigt", "baut", "erstellt", "erzeugt", "generiert", "nutzt",
    "verwendet", "verbraucht", "benötigt", "braucht", "erfordert", "hält", "ausführt", "erhält",
    "empfängt", "sendet", "versendet", "liefert", "lagert", "verfolgt", "erfasst", "dokumentiert",
    "überwacht", "misst", "prüft", "kontrolliert", "inspiziert", "validiert", "testet", "startet",
    "plant", "terminiert", "zuweist", "beschäftigt", "schult", "zertifiziert", "bedient",
    "beliefert", "versorgt", "definiert", "spezifiziert", "aktualisiert", "zahlt", "bezahlt",
    "fakturiert", "genehmigt", "bearbeitet", "unterstützt", "wartet", "repariert", "ersetzt",
    "installiert", "verpackt", "lädt", "transportiert", "verarbeitet", "montiert", "schweißt",
    "lackiert", "bewegt", "befördert", "erfüllt", "regelt", "gruppiert", "begrenzt",
    "unterzeichnet", "eröffnet", "schließt", "entwickelt", "vertreibt", "verkauft", "bietet",
    "betreut", "koordiniert", "organisiert", "überprüft", "deckt", "trägt", "gibt", "löst",
    "legt fest", "stellt her", "stellt bereit", "bietet an", "deckt ab", "löst aus",
    "weist zu",
)  # fmt: skip

STOP_FR = frozenset(
    (
        "le la les l un une des du de d et ou à au aux en dans sur pour avec par chez nous notre "
        "nos votre vos leur leurs mon ma mes est sont était étaient être été il elle ils elles on "
        "ce cet cette ces qui que quoi dont où comment combien beaucoup certains certaines tout "
        "toute tous toutes chaque nouveau nouvelle nouveaux nouvelles a ont avait avaient fait "
        "font faire aussi très plus moins vers sous là ici quand puis alors y se sa son ses ne pas "
        "donc euh bon alors"
    ).split(" ")
)
STOP_DE = frozenset(
    (
        "der die das des dem den ein eine einer eines einem einen und oder von vom zu zum zur in "
        "im an am auf für mit bei aus nach über unter wir unser unsere unserer unseren ihr ihre "
        "ihrer ihren sein seine seiner seinen ist sind war waren werden wird es sie er diese "
        "dieser dieses diesen jede jeder jedes jeden alle allen viele einige neue neuer neues "
        "neuen hat haben hatte hatten macht machen auch sehr mehr als dann dort hier wenn wo dass "
        "nicht also äh ähm"
    ).split(" ")
)

DET_FR = re.compile(
    r"^(?:(?:le|la|les|un|une|des|du|de la|de|chaque|tout|toute|tous les|toutes les|nos|notre|"
    r"vos|votre|leurs|leur|ses|son|sa|certains|certaines|plusieurs|quelques|ce|cet|cette|ces|"
    r"nouveaux|nouvelles|nouveau|nouvelle)\s+|(?:l|d)['’])",
    re.IGNORECASE,
)
DET_DE = re.compile(
    r"^(?:der|die|das|des|dem|den|ein|eine|einer|eines|einem|einen|jede|jeder|jedes|jeden|alle|"
    r"allen|unser|unsere|unserer|unseren|ihre|ihr|ihrer|ihren|seine|sein|seiner|seinen|diese|"
    r"dieser|dieses|diesen|einige|mehrere|viele|neue|neuer|neues|neuen)\s+",
    re.IGNORECASE,
)

# French plurals in `-aux` whose singular ends in `-ail`, and the other irregular plurals.
FRENCH_IRREGULAR_PLURALS = {
    "travaux": "travail",
    "vitraux": "vitrail",
    "baux": "bail",
    "émaux": "émail",
    "coraux": "corail",
    "soupiraux": "soupirail",
    "yeux": "œil",
    "aïeux": "aïeul",
    "cieux": "ciel",
}
# French singular words ending in `s` that would otherwise lose it; words ending in `x` or
# `z` and in `-ss` or `-us` are invariant by rule.
FRENCH_INVARIANT_WORDS = frozenset(
    (
        "pays bras cas tas repas mois fois bois corps temps poids avis devis colis tapis permis "
        "puits frais fonds cours concours secours recours parcours discours accès succès procès "
        "excès progrès palais relais marais rabais biais univers divers mets mars sens engrais "
        "anglais français lilas dos dessous dessus jus plus dans sous vers alors"
    ).split(" ")
)
# German plurals whose singular changes its vowel or its ending, so no suffix rule finds it.
GERMAN_IRREGULAR_PLURALS = {
    "häuser": "haus",
    "kinder": "kind",
    "bilder": "bild",
    "länder": "land",
    "felder": "feld",
    "gelder": "geld",
    "räder": "rad",
    "bänder": "band",
    "wälder": "wald",
    "fächer": "fach",
    "bücher": "buch",
    "dächer": "dach",
    "gläser": "glas",
    "güter": "gut",
    "lichter": "licht",
    "männer": "mann",
    "ämter": "amt",
    "bäder": "bad",
    "blätter": "blatt",
    "rechte": "recht",
    "firmen": "firma",
    "themen": "thema",
    "konten": "konto",
    "risiken": "risiko",
    "daten": "datum",
    "zentren": "zentrum",
    "museen": "museum",
    "kriterien": "kriterium",
    "materialien": "material",
    "prinzipien": "prinzip",
    "praktika": "praktikum",
    "visa": "visum",
    "mütter": "mutter",
    "väter": "vater",
    "töchter": "tochter",
    "brüder": "bruder",
    "städte": "stadt",
    "hände": "hand",
    "wände": "wand",
    "nächte": "nacht",
    "kräfte": "kraft",
    "züge": "zug",
    "flüsse": "fluss",
    "schlüsse": "schluss",
    "anlässe": "anlass",
    "pässe": "pass",
    "köpfe": "kopf",
    "töpfe": "topf",
    "stühle": "stuhl",
    "böden": "boden",
    "läden": "laden",
    "gärten": "garten",
    "öfen": "ofen",
    "mängel": "mangel",
    "kosten": "kosten",
    "leute": "leute",
}
# German loanword plurals in `-s`; a native word's final `s` is no plural (`Haus`, `Kurs`).
GERMAN_S_PLURALS = frozenset(
    (
        "teams jobs apps laptops tickets lkws pkws chefs clubs shops tools deals meetings "
        "workshops kits sets events parks hotels autos büros handys fotos videos konzerns pcs "
        "cafés restaurants labels accounts services clients partners"
    ).split(" ")
)
# A stem a German suffix rule leaves must have at least this many letters.
_GERMAN_MIN_STEM = 3
# French verbs whose plural is not the singular plus `-nt`.
_FRENCH_PLURALS = {
    "a": "ont",
    "est": "sont",
    "fait": "font",
    "produit": "produisent",
    "construit": "construisent",
    "conduit": "conduisent",
    "fournit": "fournissent",
    "définit": "définissent",
    "garantit": "garantissent",
    "suit": "suivent",
    "inclut": "incluent",
    "comprend": "comprennent",
    "vend": "vendent",
    "attend": "attendent",
    "dépend": "dépendent",
    "rend": "rendent",
    "contient": "contiennent",
    "détient": "détiennent",
    "maintient": "maintiennent",
    "appartient": "appartiennent",
    "intervient": "interviennent",
    "soutient": "soutiennent",
    "reçoit": "reçoivent",
    "conçoit": "conçoivent",
    "requiert": "requièrent",
    "met": "mettent",
    "émet": "émettent",
    "sert": "servent",
    "peint": "peignent",
    "régit": "régissent",
    "aboutit": "aboutissent",
}
# German verbs whose plural is not the stem plus `-en` or `-n`.
_GERMAN_PLURALS = {
    "hat": "haben",
    "ist": "sind",
    "wird": "werden",
    "misst": "messen",
    "enthält": "enthalten",
    "erhält": "erhalten",
    "hält": "halten",
    "lädt": "laden",
    "läuft": "laufen",
    "trägt": "tragen",
    "gibt": "geben",
    "gilt": "gelten",
    "fährt": "fahren",
    "nimmt": "nehmen",
    "schließt": "schließen",
    "schweißt": "schweißen",
    "ausführt": "ausführen",
    "zuweist": "zuweisen",
    "braucht": "brauchen",
}


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
DOMAIN_PREFIX_FR = re.compile(
    r"^(?:en|dans la|dans le|dans les|pour la|pour le|côté) (production|chaîne d'approvisionnement"
    r"|chaîne d’approvisionnement|approvisionnement|ventes|vente|commercial|logistique"
    r"|qualité|maintenance|finance|finances|rh|ressources humaines|personnel|ingénierie)[,:]?\s*",
    re.IGNORECASE,
)
DOMAIN_PREFIX_DE = re.compile(
    r"^(?:in der|in den|im|in|bei der|beim|bei) (produktion|lieferkette|beschaffung|vertrieb"
    r"|verkauf|logistik|qualität|wartung|instandhaltung|finanzen|finanz|personal|personalwesen"
    r"|hr|technik|engineering|entwicklung)[,:]?\s*",
    re.IGNORECASE,
)
_DOMAIN_KEYS_FR = {
    "production": "production",
    "chaîne d'approvisionnement": "supply",
    "chaîne d’approvisionnement": "supply",
    "approvisionnement": "supply",
    "ventes": "sales",
    "vente": "sales",
    "commercial": "sales",
    "logistique": "logistics",
    "qualité": "quality",
    "maintenance": "maintenance",
    "finance": "finance",
    "finances": "finance",
    "rh": "people",
    "ressources humaines": "people",
    "personnel": "people",
    "ingénierie": "engineering",
}
_DOMAIN_KEYS_DE = {
    "produktion": "production",
    "lieferkette": "supply",
    "beschaffung": "supply",
    "vertrieb": "sales",
    "verkauf": "sales",
    "logistik": "logistics",
    "qualität": "quality",
    "wartung": "maintenance",
    "instandhaltung": "maintenance",
    "finanzen": "finance",
    "finanz": "finance",
    "personal": "people",
    "personalwesen": "people",
    "hr": "people",
    "technik": "engineering",
    "engineering": "engineering",
    "entwicklung": "engineering",
}

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
_LIST_SPLIT = re.compile(r"\s*,\s*|\s+and\s+|\s+or\s+")

_SPEC_WITH_RULE_FR = re.compile(
    r"^(.+?)\s+(?:qui|que|dont)\s+(.+?)\s+(?:est|sont)\s+(?:un |une |des |d['’])?(.+)$",
    re.IGNORECASE,
)
_SPEC_FR = re.compile(
    r"^(.+?)\s+(?:est|sont|c['’]est|ce sont)\s+(?:un |une |des |d['’])?"
    r"(?:types? de |sortes? de |genres? de |formes? de |catégories? de |types? d['’]"
    r"|sortes? d['’])?(.+)$",
    re.IGNORECASE,
)
_SPEC_PREPOSITION_FR = re.compile(
    r"\s(?:par|dans|sur|à|au|aux|de|du|des|avec|en|pour|chez|vers)\s|\sd['’]", re.IGNORECASE
)
_CLAUSE_SPLIT_FR = re.compile(
    r"\s*[;]\s*|\s*,\s*(?:et\s+)?(?=(?:le|la|les|un|une|des|chaque|tous|toutes|tout|toute|nos|"
    r"notre|vos|votre|leurs|leur|ses|son|sa|ce|cet|cette|ces)\s|l['’])"
    r"|\s+et\s+(?=(?:le|la|les|un|une|des|chaque|tous|toutes|tout|toute|nos|notre|vos|votre|"
    r"leurs|leur|ses|son|sa|ce|cet|cette|ces)\s|l['’])",
    re.IGNORECASE,
)
_PREPOSITIONAL_FR = re.compile(
    r"^(.*?)\s+(à|au|aux|dans|en|sur|vers|chez|avec|pour|par|depuis|auprès de)\s+(.+)$",
    re.IGNORECASE,
)
_LIST_SPLIT_FR = re.compile(r"\s*,\s*|\s+et\s+|\s+ou\s+|\s+ainsi que\s+", re.IGNORECASE)

_SPEC_WITH_RULE_DE = re.compile(
    r"^(.+?),\s+(?:die|der|das|welche|welcher|welches)\s+(.+?),\s+(?:ist|sind)\s+"
    r"(?:ein |eine |einer )?(.+)$",
    re.IGNORECASE,
)
_SPEC_DE = re.compile(
    r"^(.+?)\s+(?:ist|sind)\s+(?:ein |eine |einer )?(?:art von |art |typ von |form von |sorte von "
    r"|arten von |typen von )?(.+)$",
    re.IGNORECASE,
)
_SPEC_PREPOSITION_DE = re.compile(
    r"\s(?:von|vom|in|im|an|am|auf|zu|zum|zur|mit|bei|für|aus|durch|nach|über|unter)\s",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_DE = re.compile(
    r"\s*[;]\s*|\s*,\s*(?:und\s+)?(?=(?:der|die|das|ein|eine|jede|jeder|jedes|alle|unser|unsere|"
    r"ihre|seine)\s)|\s+und\s+(?=(?:der|die|das|ein|eine|jede|jeder|jedes|alle|unser|unsere|"
    r"ihre|seine)\s)",
    re.IGNORECASE,
)
_PREPOSITIONAL_DE = re.compile(
    r"^(.*?)\s+(an|in|im|auf|aus|bei|mit|nach|von|zu|zum|zur|für|durch|über)\s+(.+)$",
    re.IGNORECASE,
)
_LIST_SPLIT_DE = re.compile(r"\s*,\s*|\s+und\s+|\s+oder\s+|\s+sowie\s+", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedIntent:
    kind: str
    subj: str
    obj: str
    pred: str | None = None
    rule: str | None = None


@dataclass(frozen=True)
class Grammar:
    """One language's rules: its words, verbs and sentence shapes."""

    stop: frozenset[str]
    det: re.Pattern[str]
    canon: dict[str, str]
    verb_re: re.Pattern[str]
    spec_with_rule: re.Pattern[str]
    spec: re.Pattern[str]
    spec_preposition: re.Pattern[str]
    clause_split: re.Pattern[str]
    prepositional: re.Pattern[str]
    list_split: re.Pattern[str]
    domain_prefix: re.Pattern[str]
    domain_keys: Callable[[str], str]
    # The English grammar lowercases the sentence as the reference does; the others keep its
    # casing, so a German noun keeps its capital.
    lowercase: bool


def title(s: str) -> str:
    return s[:1].upper() + s[1:]


def singular(w: str, language: Language = "en") -> str:
    """The singular of one word by the language's rule. A word that starts with a capital
    keeps it, so a German noun stays a noun."""
    if language == "fr":
        return _keep_initial(w, _french_singular(w.casefold()))
    if language == "de":
        return _keep_initial(w, _german_singular(w.casefold()))
    w = re.sub(r"ies$", "y", w, count=1)
    w = re.sub(r"(ch|sh|s|x|z)es$", r"\1", w, count=1)
    # Words ending in -ss, -us, or -as after anything but an e (gas, bias, status, class) are
    # already singular; -eas plurals (areas, ideas) still lose their s.
    if re.search(r"(ss|us|(^|[^e])as)$", w):
        return w
    return re.sub(r"([^s])s$", r"\1", w, count=1)


def clean_np(np: str, language: Language = "en") -> str:
    grammar = GRAMMARS[language]
    np = re.sub(r"^[,;:\s]+", "", re.sub(r"[.!?,;:]+$", "", np.strip()), count=1)
    guard = 0
    while grammar.det.search(np) and guard < 4:
        guard += 1
        np = grammar.det.sub("", np, count=1)
    w = [x for x in re.split(r"\s+", np) if x]
    if not w:
        return ""
    w[-1] = singular(w[-1], language)
    return " ".join(w)


def split_list(np: str, language: Language = "en") -> list[str]:
    grammar = GRAMMARS[language]
    return [x for x in (clean_np(p, language) for p in grammar.list_split.split(np)) if x]


def understand(text: str, language: Language = "en") -> list[ParsedIntent]:
    """The intents of one sentence."""
    grammar = GRAMMARS[language]
    lower = re.sub(r"[.!?]+$", "", re.sub(r"\s+", " ", text.strip()))
    if grammar.lowercase:
        lower = lower.lower()
    out: list[ParsedIntent] = []
    m = grammar.spec_with_rule.match(lower)
    if m:
        out.append(
            ParsedIntent(
                "spec",
                subj=clean_np(m[3], language),
                rule=m[2].strip(),
                obj=clean_np(m[1], language),
            )
        )
        return out
    m = grammar.spec.match(lower)
    if m and not grammar.verb_re.search(m[2]) and not grammar.spec_preposition.search(m[2]):
        out.append(
            ParsedIntent("spec", subj=clean_np(m[1], language), obj=clean_np(m[2], language))
        )
        return out
    for cl in grammar.clause_split.split(lower):
        v = None
        for mm in grammar.verb_re.finditer(cl):
            if clean_np(cl[: mm.start()], language):
                v = mm
                break
        if v is None:
            continue
        subj = clean_np(cl[: v.start()], language)
        verb = re.sub(r"\s+", " ", v[1])
        pred = grammar.canon.get(verb if grammar.lowercase else verb.lower()) or v[1]
        rest = cl[v.end() :]
        if not subj:
            continue
        pp = grammar.prepositional.match(rest)
        if pp and clean_np(pp[1], language):
            rest = pp[1]
            for obj in split_list(pp[3], language):
                out.append(ParsedIntent("rel", subj=subj, pred=f"{pred} {pp[2]}", obj=obj))
        for obj in split_list(rest, language):
            out.append(ParsedIntent("rel", subj=subj, pred=pred, obj=obj))
    return out


def domain_prefix(text: str, language: Language = "en") -> tuple[str | None, str]:
    """Strips an "In <domain>, " prefix; returns the domain key and the remaining text."""
    grammar = GRAMMARS[language]
    dm = grammar.domain_prefix.match(text.lower())
    if not dm:
        return None, text
    return grammar.domain_keys(dm[1]), text[len(dm[0]) :]


def content_words(text: str, language: Language = "en") -> list[str]:
    """Words of a sentence that can name a concept, for the fallback."""
    grammar = GRAMMARS[language]
    letters = r"[^a-z\s-]" if grammar.lowercase else r"[^\w\s-]"
    words = re.split(r"\s+", re.sub(letters, " ", text.lower()))
    return [singular(w, language) for w in words if len(w) > 3 and w not in grammar.stop]


def _english_domain_key(name: str) -> str:
    return "supply" if name.startswith("supply") else "people" if name == "hr" else name


def _french_plural(verb: str) -> str:
    """The third person plural of a French lexicon entry: its first verb inflected, a passive
    participle agreed in the plural."""
    words = verb.split(" ")
    if words[0] == "est" and len(words) > 1:
        return " ".join(["sont", words[1] + "s", *words[2:]])
    head = words[0]
    if head.startswith(("s'", "s’")) and head.endswith("e"):
        words[0] = head + "nt"
    elif head in _FRENCH_PLURALS:
        words[0] = _FRENCH_PLURALS[head]
    elif head == "se" and len(words) > 1 and words[1].endswith("e"):
        words[1] = words[1] + "nt"
    elif head.endswith("e"):
        words[0] = head + "nt"
    return " ".join(words)


def _french_agreements(verb: str) -> list[str]:
    """A passive entry with its feminine and plural agreements."""
    words = verb.split(" ")
    if words[0] != "est" or len(words) < 2:
        return [verb, _french_plural(verb)]
    participle = words[1]
    rest = words[2:]
    return [
        " ".join(["est", participle, *rest]),
        " ".join(["est", participle + "e", *rest]),
        " ".join(["sont", participle + "s", *rest]),
        " ".join(["sont", participle + "es", *rest]),
    ]


def _german_plural(verb: str) -> str:
    """The third person plural of a German lexicon entry: its first verb inflected."""
    words = verb.split(" ")
    head = words[0]
    if head in _GERMAN_PLURALS:
        words[0] = _GERMAN_PLURALS[head]
    elif head.endswith("et"):
        words[0] = head[:-2] + "en"
    elif head.endswith("t"):
        stem = head[:-1]
        words[0] = stem + ("n" if stem.endswith(("er", "el")) else "en")
    return " ".join(words)


def _variants_of(lexicon: tuple[str, ...], forms: Callable[[str], list[str]]) -> dict[str, str]:
    """Every surface form of the lexicon mapped to its canonical action."""
    canon: dict[str, str] = {}
    for verb in lexicon:
        for form in forms(verb):
            canon.setdefault(form, verb)
    return canon


def _verb_pattern(forms: list[str]) -> re.Pattern[str]:
    return re.compile(
        r"(?<!\w)("
        + "|".join(
            re.sub(r"\s+", r"\\s+", re.escape(v)) for v in sorted(forms, key=len, reverse=True)
        )
        + r")(?!\w)",
        re.IGNORECASE,
    )


def _keep_initial(original: str, singular_form: str) -> str:
    if original[:1].isupper() and singular_form:
        return singular_form[0].upper() + singular_form[1:]
    return singular_form


def _french_singular(word: str) -> str:
    if word in FRENCH_INVARIANT_WORDS:
        return word
    found = FRENCH_IRREGULAR_PLURALS.get(word)
    if found is not None:
        return found
    if len(word) > 4 and word.endswith("eaux"):
        return word[:-1]
    if len(word) > 4 and word.endswith("aux"):
        return word[:-3] + "al"
    if len(word) > 3 and word.endswith(("eux", "oux")):
        return word[:-1]
    if word.endswith(("x", "z", "ss", "us")):
        return word
    if len(word) > 2 and word.endswith("s"):
        return word[:-1]
    return word


def _german_singular(word: str) -> str:
    found = GERMAN_IRREGULAR_PLURALS.get(word)
    if found is not None:
        return found
    if word in GERMAN_S_PLURALS:
        return word[:-1]
    if word.endswith("innen") and len(word) - 3 >= _GERMAN_MIN_STEM:
        return word[:-3]
    for suffix in ("en", "e", "n"):
        if word.endswith(suffix) and len(word) - len(suffix) >= _GERMAN_MIN_STEM:
            return word[: -len(suffix)]
    if word.endswith("s") and len(word) > 3 and word[-2] in "aeiouy":
        return word[:-1]
    return word


_CANON_FR = _variants_of(VERBS_LEX_FR, _french_agreements)
_CANON_DE = _variants_of(VERBS_LEX_DE, lambda v: [v, _german_plural(v)])

GRAMMARS: dict[Language, Grammar] = {
    "en": Grammar(
        stop=STOP,
        det=DET,
        canon=CANON,
        verb_re=VERB_RE,
        spec_with_rule=_SPEC_WITH_RULE,
        spec=_SPEC,
        spec_preposition=_SPEC_PREPOSITION,
        clause_split=_CLAUSE_SPLIT,
        prepositional=_PREPOSITIONAL,
        list_split=_LIST_SPLIT,
        domain_prefix=DOMAIN_PREFIX,
        domain_keys=_english_domain_key,
        lowercase=True,
    ),
    "fr": Grammar(
        stop=STOP_FR,
        det=DET_FR,
        canon=_CANON_FR,
        verb_re=_verb_pattern(list(_CANON_FR)),
        spec_with_rule=_SPEC_WITH_RULE_FR,
        spec=_SPEC_FR,
        spec_preposition=_SPEC_PREPOSITION_FR,
        clause_split=_CLAUSE_SPLIT_FR,
        prepositional=_PREPOSITIONAL_FR,
        list_split=_LIST_SPLIT_FR,
        domain_prefix=DOMAIN_PREFIX_FR,
        domain_keys=lambda name: _DOMAIN_KEYS_FR[name],
        lowercase=False,
    ),
    "de": Grammar(
        stop=STOP_DE,
        det=DET_DE,
        canon=_CANON_DE,
        verb_re=_verb_pattern(list(_CANON_DE)),
        spec_with_rule=_SPEC_WITH_RULE_DE,
        spec=_SPEC_DE,
        spec_preposition=_SPEC_PREPOSITION_DE,
        clause_split=_CLAUSE_SPLIT_DE,
        prepositional=_PREPOSITIONAL_DE,
        list_split=_LIST_SPLIT_DE,
        domain_prefix=DOMAIN_PREFIX_DE,
        domain_keys=lambda name: _DOMAIN_KEYS_DE[name],
        lowercase=False,
    ),
}
