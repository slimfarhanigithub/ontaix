"""Entra ID bearer tokens for the keyless Azure AI Foundry clients, cached until near expiry.

One `EntraTokenCache` per scope serves every client of the process. A token is handed out from
memory while it is valid; once it is within `REFRESH_BEFORE_SECONDS` of expiry a background
refresh replaces it, and callers keep the current token meanwhile. A call waits for the
credential only when no token is held or the held one is within `EXPIRY_MARGIN_SECONDS` of
expiry.

A refresh is one shared task: concurrent callers wait on the same acquisition, and a caller
that gives up (its own timeout) leaves the task running, so the token it brings still lands in
the cache. A failed credential call is tried once more after `RETRY_BACKOFF_SECONDS`. A refresh
that fails never drops a held token: the token is served until its real expiry, and no new
background refresh starts for `FAILURE_COOLDOWN_SECONDS`. The refresh task belongs to the
event loop that started it; a call from another loop starts its own.

The credential (`DefaultAzureCredential`: workload identity in the cluster, the Azure CLI
locally, given `CLI_PROCESS_TIMEOUT_SECONDS` per run) runs in a worker thread, since the Azure
CLI takes seconds per token. Tokens and the credential chain's messages, which name
environment and account details, are never logged: a failure logs its exception type once.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# A refresh starts in the background this long before expiry.
REFRESH_BEFORE_SECONDS = 300.0
# A token this close to expiry is handed out only when no fresh one can be acquired.
EXPIRY_MARGIN_SECONDS = 60.0
# The wait before the one retry of a failed credential call.
RETRY_BACKOFF_SECONDS = 1.0
# After a failed refresh, a held token is served without a new attempt for this long.
FAILURE_COOLDOWN_SECONDS = 30.0
# The Azure CLI and the other developer credentials may run this long per token.
CLI_PROCESS_TIMEOUT_SECONDS = 30


class _AccessToken(Protocol):
    token: str
    expires_on: int


class _Credential(Protocol):
    def get_token(self, *scopes: str) -> _AccessToken: ...


class EntraTokenCache:
    """Bearer tokens of one scope from one credential, cached and refreshed ahead of expiry."""

    def __init__(
        self,
        scope: str,
        credential_factory: Callable[[], _Credential],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._scope = scope
        self._credential_factory = credential_factory
        self._credential: _Credential | None = None
        self._clock = clock
        self._token: str | None = None
        self._expires_on = 0.0
        self._failed_at: float | None = None
        self._refreshing: asyncio.Task[None] | None = None

    async def token(self) -> str:
        """A valid bearer token; waits for the credential only when none is held or the held one
        is about to expire, and serves a held token until its real expiry when that wait fails."""
        now = self._clock()
        if self._token is not None and now < self._expires_on - EXPIRY_MARGIN_SECONDS:
            if now >= self._expires_on - REFRESH_BEFORE_SECONDS and not self._cooling_down(now):
                self._start_refresh()
            return self._token
        if self._token is not None and now < self._expires_on and self._cooling_down(now):
            return self._token
        try:
            await asyncio.shield(self._start_refresh())
        except Exception:
            if self._token is not None and self._clock() < self._expires_on:
                return self._token
            raise
        assert self._token is not None
        return self._token

    async def warm(self) -> None:
        """Acquires a token ahead of the first call."""
        await self.token()

    def _cooling_down(self, now: float) -> bool:
        return self._failed_at is not None and now - self._failed_at < FAILURE_COOLDOWN_SECONDS

    def _start_refresh(self) -> asyncio.Task[None]:
        """The running refresh of this event loop, or a new one."""
        task = self._refreshing
        if task is None or task.done() or task.get_loop() is not asyncio.get_running_loop():
            task = asyncio.create_task(self._refresh(), name="entra-token-refresh")
            # The exception is logged by `_refresh`; retrieving it here keeps a background
            # refresh nobody awaits from being reported as unhandled.
            task.add_done_callback(_retrieve_exception)
            self._refreshing = task
        return task

    async def _refresh(self) -> None:
        started = time.perf_counter()
        try:
            try:
                access = await asyncio.to_thread(self._get_token)
            except Exception as exc:
                logger.debug("entra token attempt failed: %s; retrying", type(exc).__name__)
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                access = await asyncio.to_thread(self._get_token)
        except Exception as exc:
            self._failed_at = self._clock()
            held = self._token is not None and self._clock() < self._expires_on
            logger.warning(
                "no Entra ID token was acquired after 2 attempts (%s); %s",
                type(exc).__name__,
                "the held token is served until it expires" if held else "no token is held",
            )
            raise
        self._token, self._expires_on = access.token, float(access.expires_on)
        self._failed_at = None
        logger.debug("entra token acquired in %d ms", int((time.perf_counter() - started) * 1000))

    def _get_token(self) -> _AccessToken:
        if self._credential is None:
            self._credential = self._credential_factory()
        return self._credential.get_token(self._scope)


@functools.cache
def shared_token_cache(scope: str) -> EntraTokenCache:
    """The process-wide token cache of `scope`, over `DefaultAzureCredential`."""
    return EntraTokenCache(scope, _default_credential)


def _default_credential() -> Any:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(process_timeout=CLI_PROCESS_TIMEOUT_SECONDS)


def _retrieve_exception(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        task.exception()
