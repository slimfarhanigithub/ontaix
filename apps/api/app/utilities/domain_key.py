"""A tenant domain's key derived from its name, and the rules its name and owner text follow."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

from app.utilities.action_text import has_refused_character

MAX_DOMAINS = 64
MAX_DOMAIN_KEY_LENGTH = 40
MAX_DOMAIN_NAME_LENGTH = 60
MAX_DOMAIN_OWNER_LENGTH = 60
FALLBACK_KEY = "domain"

_NON_KEY_CHARACTERS = re.compile(r"[^a-z0-9]+")


def derive_domain_key(name: str, taken: Collection[str]) -> str:
    """The key for a domain called `name`: lower-case ASCII letters, digits and `_`, starting
    with a letter, 2 to 40 characters, and not in `taken` (a numbered suffix makes it unique)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    base = _NON_KEY_CHARACTERS.sub("_", ascii_name.lower()).strip("_")
    if not base:
        base = FALLBACK_KEY
    if not base[0].isalpha():
        base = f"d_{base}"
    if len(base) < 2:
        base = f"{base}_{FALLBACK_KEY}"
    base = base[:MAX_DOMAIN_KEY_LENGTH].rstrip("_")
    candidate = base
    ordinal = 2
    while candidate in taken:
        suffix = f"_{ordinal}"
        candidate = base[: MAX_DOMAIN_KEY_LENGTH - len(suffix)].rstrip("_") + suffix
        ordinal += 1
    return candidate


def domain_name_problem(name: str) -> str | None:
    """Why `name` cannot name a domain, or None: 1 to 60 characters, no surrounding space, no
    markup, control or format characters."""
    if not 1 <= len(name) <= MAX_DOMAIN_NAME_LENGTH:
        return f"a domain name has 1 to {MAX_DOMAIN_NAME_LENGTH} characters"
    if name != name.strip():
        return "a domain name has no surrounding space"
    if has_refused_character(name):
        return "a domain name holds no markup, control or format characters"
    return None


def domain_owner_problem(owner: str) -> str | None:
    """Why `owner` cannot be a domain's owner text, or None: at most 60 characters, no markup,
    control or format characters."""
    if len(owner) > MAX_DOMAIN_OWNER_LENGTH:
        return f"an owner has at most {MAX_DOMAIN_OWNER_LENGTH} characters"
    if has_refused_character(owner):
        return "an owner holds no markup, control or format characters"
    return None


def same_name(a: str, b: str) -> bool:
    """Domain names are unique case-insensitively."""
    return a.lower() == b.lower()
