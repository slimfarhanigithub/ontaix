"""Session and CSRF tokens, their stored digests and constant-time comparison.

A token is 256 random bits in unpadded base64url (43 characters). The database stores only the
SHA-256 of a session token, so a read of `auth_session` never yields a usable cookie.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata

TOKEN_BYTES = 32
TOKEN_LENGTH = 43


def new_token() -> str:
    """A fresh 256-bit random token, 43 base64url characters."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> bytes:
    """The SHA-256 of a presented token: what `auth_session.token_hash` holds."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def is_well_formed(token: str | None) -> bool:
    """True for a string of the issued length and alphabet; anything else is never looked up."""
    return (
        token is not None
        and len(token) == TOKEN_LENGTH
        and all(c.isascii() and (c.isalnum() or c in "-_") for c in token)
    )


def tokens_equal(presented: str | None, expected: str) -> bool:
    """Constant-time comparison; a missing value never matches."""
    if presented is None:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def normalize_email(email: str) -> str:
    """Trimmed, NFC-normalised and lower-cased: the form accounts are stored and looked up in."""
    return unicodedata.normalize("NFC", email.strip()).lower()


def key_digest(value: str) -> bytes:
    """The SHA-256 of a throttle key (a normalised email or a client IP)."""
    return hashlib.sha256(value.encode("utf-8")).digest()
