"""Password hashing, the password policy, tokens and the client IP: pure units, no database."""

from __future__ import annotations

import asyncio
import time
import unicodedata

import pytest
from argon2 import PasswordHasher, Type

from app.services import password_hash_service, password_policy_service
from app.utilities.client_ip import client_ip
from app.utilities.session_tokens import (
    TOKEN_LENGTH,
    is_well_formed,
    key_digest,
    new_token,
    normalize_email,
    token_digest,
    tokens_equal,
)
from tests.conftest import generated_password

# Entries of the bundled NCSC list of the most common breached passwords, 12 characters or more.
COMMON = ("qwerty123456", "1qaz2wsx3edc", "123456qwerty")


async def test_hash_is_argon2id_with_the_decided_parameters() -> None:
    password = generated_password()
    phc = await password_hash_service.hash_password(password)

    assert phc.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert password not in phc
    assert await password_hash_service.verify_password(phc, password)
    assert not await password_hash_service.verify_password(phc, password + "x")
    assert not password_hash_service.needs_rehash(phc)


async def test_hash_of_older_parameters_verifies_and_needs_rehash() -> None:
    password = generated_password()
    weaker = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1, type=Type.ID)
    phc = weaker.hash(password)

    assert await password_hash_service.verify_password(phc, password)
    assert password_hash_service.needs_rehash(phc)


async def test_passwords_are_compared_after_nfc_normalisation() -> None:
    composed = "café-" + generated_password()
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    phc = await password_hash_service.hash_password(composed)

    assert await password_hash_service.verify_password(phc, decomposed)


async def test_no_hash_still_verifies_against_the_dummy_and_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original = password_hash_service._verify

    def counting(phc: str, password: str) -> bool:
        calls.append(phc)
        return original(phc, password)

    monkeypatch.setattr(password_hash_service, "_verify", counting)
    phc = await password_hash_service.hash_password(generated_password())

    assert not await password_hash_service.verify_password(None, generated_password())
    assert not await password_hash_service.verify_password(phc, generated_password())
    assert len(calls) == 2, "an unknown account costs one argon2id verification like a known one"
    assert calls[0].startswith("$argon2id$v=19$m=65536,t=3,p=4$")


async def test_at_most_four_hashes_run_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    running = peak = 0

    def slow_hash(password: str) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1
        return "$argon2id$stub"

    class Stub:
        hash = staticmethod(slow_hash)

    monkeypatch.setattr(password_hash_service, "_HASHER", Stub)
    await asyncio.gather(*(password_hash_service.hash_password("p") for _ in range(12)))

    assert peak <= password_hash_service.MAX_CONCURRENT_HASHES


@pytest.mark.parametrize(
    ("length", "refusal"),
    [(11, password_policy_service.TOO_SHORT), (129, password_policy_service.TOO_LONG)],
)
async def test_length_is_12_to_128_characters(length: int, refusal: str) -> None:
    password = (generated_password() * 10)[:length]

    assert await password_policy_service.refusal(password, "ada@example.test") == refusal


async def test_length_counts_characters_after_nfc() -> None:
    twelve_composed = "é" * 12
    eleven_composed = unicodedata.normalize("NFD", "é" * 11)
    assert len(eleven_composed) == 22

    assert await password_policy_service.refusal(twelve_composed, "x@y.test") is None
    assert (
        await password_policy_service.refusal(eleven_composed, "x@y.test")
        == password_policy_service.TOO_SHORT
    )


@pytest.mark.parametrize("password", [*COMMON, "QWERTY123456", "Qwerty123456"])
async def test_common_breached_passwords_are_refused_in_any_case(password: str) -> None:
    assert (
        await password_policy_service.refusal(password, "ada@example.test")
        == password_policy_service.TOO_COMMON
    )


async def test_the_email_local_part_is_refused() -> None:
    password = "Ada.Lovelace-" + generated_password()

    assert (
        await password_policy_service.refusal(password, "ada.lovelace@example.test")
        == password_policy_service.CONTAINS_EMAIL
    )


async def test_a_short_local_part_bans_nothing() -> None:
    assert await password_policy_service.refusal("ab" + generated_password(), "ab@x.test") is None


async def test_the_current_password_is_refused() -> None:
    current = generated_password()
    phc = await password_hash_service.hash_password(current)

    assert (
        await password_policy_service.refusal(current, "ada@example.test", phc)
        == password_policy_service.SAME_AS_CURRENT
    )
    assert await password_policy_service.refusal(generated_password(), "ada@x.test", phc) is None


def test_the_bundled_list_holds_the_top_100k() -> None:
    keys = password_policy_service._keys()

    assert len(keys) > 95_000
    assert keys == sorted(keys)


def test_session_tokens_are_256_bit_and_stored_as_sha256() -> None:
    token = new_token()

    assert len(token) == TOKEN_LENGTH and is_well_formed(token)
    assert token != new_token()
    assert len(token_digest(token)) == 32
    assert not is_well_formed(token[:-1]) and not is_well_formed(token[:-1] + "!")
    assert tokens_equal(token, token) and not tokens_equal(None, token)
    assert not tokens_equal(new_token(), token)


def test_throttle_keys_are_digests_of_the_normalised_email() -> None:
    assert normalize_email("  Ada@Example.TEST ") == "ada@example.test"
    assert key_digest(normalize_email("ADA@example.test")) == key_digest("ada@example.test")


@pytest.mark.parametrize(
    ("forwarded", "peer", "hops", "expected"),
    [
        (None, "10.0.0.9", 0, "10.0.0.9"),
        ("203.0.113.7", "10.0.0.9", 0, "10.0.0.9"),
        ("203.0.113.7", "10.0.0.9", 1, "203.0.113.7"),
        ("198.51.100.1, 203.0.113.7", "10.0.0.9", 1, "203.0.113.7"),
        ("198.51.100.1, 203.0.113.7", "10.0.0.9", 2, "198.51.100.1"),
        ("not-an-ip", "10.0.0.9", 1, None),
        ("203.0.113.7", "10.0.0.9", 3, "10.0.0.9"),
    ],
)
def test_client_ip_trusts_only_the_configured_proxy_hops(
    forwarded: str | None, peer: str, hops: int, expected: str | None
) -> None:
    assert client_ip(forwarded, peer, hops) == expected
