"""The Entra ID token cache: served from memory, refreshed ahead of expiry, never blocking a
call while a valid token is held. The credential is a fake; no token here is real."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

import pytest

import app.clients.entra_token_client as entra_token_client
import app.clients.llm_client as llm_client
from app.clients.entra_token_client import (
    CLI_PROCESS_TIMEOUT_SECONDS,
    EXPIRY_MARGIN_SECONDS,
    FAILURE_COOLDOWN_SECONDS,
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
    """Hands out `t1`, `t2`, ... each valid for an hour from the fake clock; the next `failures`
    calls fail as the Azure CLI does when it cannot be invoked."""

    def __init__(self, clock: list[float], gate: threading.Event | None = None) -> None:
        self.clock = clock
        self.calls = 0
        self.attempts = 0
        self.failures = 0
        self.gate = gate

    def get_token(self, *scopes: str) -> _Token:
        assert scopes == (SCOPE,)
        if self.gate is not None:
            self.gate.wait(5)
        self.attempts += 1
        if self.failures:
            self.failures -= 1
            raise RuntimeError("Failed to invoke the Azure CLI (account details)")
        self.calls += 1
        return _Token(f"t{self.calls}", int(self.clock[0]) + LIFETIME)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entra_token_client, "RETRY_BACKOFF_SECONDS", 0.0)


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


@pytest.mark.asyncio(loop_scope="session")
async def test_a_failed_credential_call_is_retried_once() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    credential.failures = 1
    cache = cache_with(credential, clock)

    assert await cache.token() == "t1"
    assert credential.attempts == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_a_failed_background_refresh_keeps_the_valid_token(caplog) -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)
    assert await cache.token() == "t1"
    credential.failures = 2

    clock[0] += LIFETIME - REFRESH_BEFORE_SECONDS + 1
    assert await cache.token() == "t1"
    assert cache._refreshing is not None
    with pytest.raises(RuntimeError):
        await cache._refreshing

    # While the failure cools down, the held token is served with no new attempt.
    clock[0] += FAILURE_COOLDOWN_SECONDS - 1
    assert await cache.token() == "t1"
    assert credential.attempts == 3
    [warning] = [r for r in caplog.records if r.levelname == "WARNING"]
    assert "RuntimeError" in warning.getMessage()
    assert "account details" not in caplog.text

    # Once the cooldown passes, a new background refresh brings a fresh token.
    clock[0] += 2
    assert await cache.token() == "t1"
    await cache._refreshing
    assert await cache.token() == "t2"


@pytest.mark.asyncio(loop_scope="session")
async def test_a_token_about_to_expire_is_served_when_its_refresh_fails() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)
    await cache.token()
    credential.failures = 2

    clock[0] += LIFETIME - EXPIRY_MARGIN_SECONDS + 1

    assert await cache.token() == "t1"
    assert credential.attempts == 3


@pytest.mark.asyncio(loop_scope="session")
async def test_an_expired_token_and_a_failing_credential_raise() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)
    await cache.token()
    credential.failures = 2

    clock[0] += LIFETIME + 1

    with pytest.raises(RuntimeError):
        await cache.token()
    assert credential.attempts == 3


def test_a_refresh_from_another_event_loop_starts_its_own_task() -> None:
    clock = [1_000_000.0]
    credential = FakeCredential(clock)
    cache = cache_with(credential, clock)

    assert asyncio.run(cache.token()) == "t1"
    clock[0] += LIFETIME + 1
    # The first loop is closed; its finished task is not reused.
    assert asyncio.run(cache.token()) == "t2"


def test_the_default_credential_gives_the_azure_cli_a_longer_timeout(monkeypatch) -> None:
    import azure.identity

    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> object:
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", fake)
    entra_token_client._default_credential()
    assert seen == {"process_timeout": CLI_PROCESS_TIMEOUT_SECONDS}


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
