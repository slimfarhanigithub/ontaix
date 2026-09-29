"""Entra ID bearer tokens for the keyless Azure AI Foundry clients, cached until near expiry.

One `EntraTokenCache` per scope serves every client of the process. A token is handed out from
memory while it is valid; once it is within `REFRESH_BEFORE_SECONDS` of expiry a single
background refresh replaces it, and callers keep the current token meanwhile. A call waits for
the credential only when no token is held or the held one is within `EXPIRY_MARGIN_SECONDS` of
expiry. The credential (`DefaultAzureCredential`: workload identity in the cluster, the Azure
CLI locally) runs in a worker thread, since the Azure CLI takes seconds per token. Tokens are
never logged.
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
# A token this close to expiry is not handed out; the caller waits for a fresh one.
EXPIRY_MARGIN_SECONDS = 60.0


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
        self._lock: asyncio.Lock | None = None
        self._refreshing: asyncio.Task[None] | None = None

    async def token(self) -> str:
        """A valid bearer token; waits for the credential only when none is held."""
        now = self._clock()
        if self._token is not None and now < self._expires_on - EXPIRY_MARGIN_SECONDS:
            if now >= self._expires_on - REFRESH_BEFORE_SECONDS:
                self._refresh_in_background()
            return self._token
        await self._refresh()
        assert self._token is not None
        return self._token

    async def warm(self) -> None:
        """Acquires a token ahead of the first call."""
        await self.token()

    def _refresh_in_background(self) -> None:
        if self._refreshing is None or self._refreshing.done():
            self._refreshing = asyncio.create_task(self._refresh(), name="entra-token-refresh")
            self._refreshing.add_done_callback(_log_failed_refresh)

    async def _refresh(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        acquired_before = self._expires_on
        async with self._lock:
            # A refresh that finished while this one waited already did the work.
            if self._expires_on != acquired_before and self._usable():
                return
            started = time.perf_counter()
            access = await asyncio.to_thread(self._get_token)
            self._token, self._expires_on = access.token, float(access.expires_on)
            logger.debug(
                "entra token acquired in %d ms", int((time.perf_counter() - started) * 1000)
            )

    def _usable(self) -> bool:
        return self._token is not None and self._clock() < self._expires_on - EXPIRY_MARGIN_SECONDS

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

    return DefaultAzureCredential()


def _log_failed_refresh(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning(
            "a background Entra ID token refresh failed: %s", type(task.exception()).__name__
        )
