"""The Entra ID token cache: served from memory, refreshed ahead of expiry, never blocking a
call while a valid token is held. The credential is a fake; no token here is real."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

import pytest

import app.clients.llm_client as llm_client
from app.clients.entra_token_client import (
    EXPIRY_MARGIN_SECONDS,
    REFRESH_BEFORE_SECONDS,
    EntraTokenCache,
    shared_token_cache,
)

SCOPE = "https://ai.azure.com/.default"
LIFETIME = 3600


@dataclass
class _Token:
    token: str
    expires_on: int


class FakeCredential:
    """Hands out `t1`, `t2`, ... each valid for an hour from the fake clock."""

    def __init__(self, clock: list[float], gate: threading.Event | None = None) -> None:
        self.clock = clock
        self.calls = 0
        self.gate = gate

    def get_token(self, *scopes: str) -> _Token:
        assert scopes == (SCOPE,)
        if self.gate is not None:
            self.gate.wait(5)
        self.calls += 1
        return _Token(f"t{self.calls}", int(self.clock[0]) + LIFETIME)


def cache_with(credential: FakeCredential, clock: list[float]) -> EntraTokenCache:
    return EntraTokenCache(SCOPE, lambda: credential, clock=lambda: clock[0])


@pytest.mark.asyncio(loop_scope="session")
async def test_a_valid_token_is_served_from_memory() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)

    tokens = [await cache.token() for _ in range(5)]
    clock[0] += LIFETIME - REFRESH_BEFORE_SECONDS - 1
    tokens.append(await cache.token())

    assert tokens == ["t1"] * 6
    assert credential.calls == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_a_token_near_expiry_is_refreshed_in_the_background_without_blocking() -> None:
    clock = [1_000_000.0]
    gate = threading.Event()
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)
    assert await cache.token() == "t1"
    credential.gate = gate

    clock[0] += LIFETIME - REFRESH_BEFORE_SECONDS + 1
    # The credential is held back: the call still answers at once with the current token.
    served = await asyncio.wait_for(cache.token(), timeout=1)
    assert served == "t1"
    assert await cache.token() == "t1"
    gate.set()
    assert cache._refreshing is not None
    await asyncio.wait_for(cache._refreshing, timeout=5)

    assert await cache.token() == "t2"
    assert credential.calls == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_an_expiring_token_is_never_handed_out() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)
    await cache.token()

    clock[0] += LIFETIME - EXPIRY_MARGIN_SECONDS + 1

    assert await cache.token() == "t2"
    assert credential.calls == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_first_calls_share_one_acquisition() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)

    tokens = await asyncio.gather(*(cache.token() for _ in range(8)))

    assert tokens == ["t1"] * 8
    assert credential.calls == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_warm_acquires_the_token_ahead_of_the_first_call() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)

    await cache.warm()

    assert credential.calls == 1
    assert await cache.token() == "t1"
    assert credential.calls == 1


def test_every_client_of_a_scope_shares_one_cache() -> None:
    assert shared_token_cache(SCOPE) is shared_token_cache(SCOPE)
    assert shared_token_cache(SCOPE) is not shared_token_cache("https://other/.default")


class _Warmable:
    provider, model = "fake", "fake-model"

    def __init__(self, fails: bool = False) -> None:
        self.warmed = 0
        self.fails = fails

    async def warm(self) -> None:
        self.warmed += 1
        if self.fails:
            raise ConnectionError("unreachable")


@pytest.mark.asyncio(loop_scope="session")
async def test_start_up_warms_each_profile_and_survives_a_failure() -> None:
    live, deep = _Warmable(), _Warmable(fails=True)
    llm_client.set_llm_client(live, "live")  # type: ignore[arg-type]
    llm_client.set_llm_client(deep, "deep")  # type: ignore[arg-type]

    await llm_client.warm_llm_clients()

    assert (live.warmed, deep.warmed) == (1, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_start_up_skips_clients_without_a_warm_up() -> None:
    llm_client.set_llm_client(object(), "live")  # type: ignore[arg-type]
    llm_client.set_llm_client(None, "deep")

    await llm_client.warm_llm_clients()
