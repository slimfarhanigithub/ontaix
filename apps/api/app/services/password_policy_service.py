"""The password policy (NIST SP 800-63B): length, a breached-password list, and two rules about
the account. No composition rules and no expiry.

A new password is refused when, after NFC normalisation, it is shorter than 12 or longer than
128 characters, appears in the bundled list of the most common breached passwords, contains the
local part of the account's email (when that part has at least 3 characters, so a one-letter
name never bans a letter), or equals the current password.

The list is `app/data/common_passwords.bin`: the first 8 bytes of the SHA-256 of each
case-folded, NFC-normalised entry of the NCSC "100k most used passwords" list (from Have I Been
Pwned, via SecLists), sorted, 97,746 distinct keys. It is checked in memory with no network call,
and holds no password in clear. Comparison is case-insensitive, so `Qwerty123456` is as common
as `qwerty123456`.
"""

from __future__ import annotations

import bisect
import hashlib
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.services import password_hash_service

logger = logging.getLogger(__name__)

MIN_LENGTH = 12
MAX_LENGTH = 128
KEY_BYTES = 8
MIN_LOCAL_PART = 3
COMMON_PASSWORDS_FILE = Path(__file__).resolve().parents[1] / "data" / "common_passwords.bin"

TOO_SHORT = "Use at least 12 characters."
TOO_LONG = "Use at most 128 characters."
TOO_COMMON = "This password is too common. Choose another."
SAME_AS_CURRENT = "Choose a password different from the current one."
CONTAINS_EMAIL = "The password must not contain your email name."


async def refusal(password: str, email: str, current_hash: str | None = None) -> str | None:
    """Why the password is refused, as the sentence the Studio shows; None when it passes."""
    normalized = unicodedata.normalize("NFC", password)
    if len(normalized) < MIN_LENGTH:
        return TOO_SHORT
    if len(normalized) > MAX_LENGTH:
        return TOO_LONG
    if is_common(normalized):
        return TOO_COMMON
    local = unicodedata.normalize("NFC", email).split("@", 1)[0].casefold()
    if len(local) >= MIN_LOCAL_PART and local in normalized.casefold():
        return CONTAINS_EMAIL
    if current_hash is not None and await password_hash_service.verify_password(
        current_hash, normalized
    ):
        return SAME_AS_CURRENT
    return None


def is_common(password: str) -> bool:
    """True when the password is in the bundled breached-password list, ignoring case."""
    key = _key(password)
    keys = _keys()
    index = bisect.bisect_left(keys, key)
    return index < len(keys) and keys[index] == key


def _key(password: str) -> bytes:
    folded = unicodedata.normalize("NFC", password).casefold()
    return hashlib.sha256(folded.encode("utf-8")).digest()[:KEY_BYTES]


@lru_cache(maxsize=1)
def _keys() -> list[bytes]:
    data = COMMON_PASSWORDS_FILE.read_bytes()
    if not data or len(data) % KEY_BYTES:
        raise RuntimeError(f"{COMMON_PASSWORDS_FILE.name} is missing or damaged")
    return [data[i : i + KEY_BYTES] for i in range(0, len(data), KEY_BYTES)]
