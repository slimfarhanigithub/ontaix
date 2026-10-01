"""argon2id hashing of passwords, bounded so hashing cannot exhaust the process's memory.

Parameters are RFC 9106's second recommended set: 64 MiB of memory, 3 iterations, parallelism 4,
a 16-byte salt and a 32-byte tag, above OWASP's minimum of 19 MiB and 2 iterations. The PHC
string keeps them, so a hash made with other parameters still verifies and is flagged for
rehashing. At most 4 hashes run at once per process (256 MiB at peak), each in a worker thread
so the event loop keeps serving. Passwords are NFC-normalised first and never logged.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import unicodedata
import weakref
from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

logger = logging.getLogger(__name__)

TIME_COST = 3
MEMORY_COST_KIB = 64 * 1024
PARALLELISM = 4
HASH_LENGTH = 32
SALT_LENGTH = 16
MAX_CONCURRENT_HASHES = 4

_HASHER = PasswordHasher(
    time_cost=TIME_COST,
    memory_cost=MEMORY_COST_KIB,
    parallelism=PARALLELISM,
    hash_len=HASH_LENGTH,
    salt_len=SALT_LENGTH,
    type=Type.ID,
)
_slots_by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


async def hash_password(password: str) -> str:
    """The PHC string of a new argon2id hash of the NFC-normalised password."""
    normalized = _normalize(password)
    async with _slots():
        return await asyncio.to_thread(_HASHER.hash, normalized)


async def verify_password(password_hash: str | None, password: str) -> bool:
    """True when the password matches. Without a hash (no account, or no credential) the
    password is verified against a fixed dummy hash, so every refusal costs the same work."""
    target = password_hash or await _dummy_hash()
    normalized = _normalize(password)
    async with _slots():
        matched = await asyncio.to_thread(_verify, target, normalized)
    return matched and password_hash is not None


async def warm() -> None:
    """Compute the dummy hash ahead of the first sign-in, so no request pays for it."""
    await _dummy_hash()


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with other parameters than the current ones."""
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        logger.warning("a stored password hash could not be verified")
        return False


def _slots() -> asyncio.Semaphore:
    """The hashing slots of the running event loop."""
    loop = asyncio.get_running_loop()
    slots = _slots_by_loop.get(loop)
    if slots is None:
        slots = _slots_by_loop[loop] = asyncio.Semaphore(MAX_CONCURRENT_HASHES)
    return slots


@lru_cache(maxsize=1)
def _dummy_hash_value() -> str:
    return _HASHER.hash(secrets.token_urlsafe(32))


async def _dummy_hash() -> str:
    return await asyncio.to_thread(_dummy_hash_value)


def _normalize(password: str) -> str:
    return unicodedata.normalize("NFC", password)
