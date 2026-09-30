"""Azure AI Speech tokens for the browser's recogniser, exchanged server-side and keyless.

The API takes a Microsoft Entra access token for `https://cognitiveservices.azure.com/.default`
and exchanges it at the Speech resource's own `sts/v1.0/issueToken` endpoint for a Speech token.
The browser receives only that Speech token: it is valid for about 10 minutes on this one Speech
resource and for nothing else. The Entra token, valid on every Azure AI services resource where
its identity holds a role, never leaves the server.

The Entra token comes from one credential:

- `ManagedIdentityCredential` with `ONTAIX_SPEECH_CLIENT_ID`, the dedicated identity that holds
  roles on the Speech resource only; in the cluster it exchanges the pod's projected service
  account token (Kubernetes workload identity). Its credential caches its token until it nears
  expiry.
- Otherwise `AzureCliCredential` (the developer's `az login`), only in `dev` and only when no
  `AZURE_FEDERATED_TOKEN_FILE` is set, so a pod never falls back to it.

With neither, no client exists and the API answers 503. Tokens are never logged: the Azure,
MSAL and HTTP loggers are held at WARNING and filtered, and a failure keeps only its exception
type or the STS status code.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from azure.core.credentials import TokenCredential

from app.clients.llm_log_redaction import protect_loggers
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
ISSUE_TOKEN_PATH = "/sts/v1.0/issueToken"
STS_TIMEOUT_SECONDS = 10.0
# Lifetime assumed when the Speech token carries no readable `exp` claim; the service issues
# tokens valid for 10 minutes, so a shorter value only makes the Studio refresh sooner.
DEFAULT_STS_LIFETIME_SECONDS = 9 * 60
_MAX_STS_TOKEN_CHARS = 8192
_STS_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._-]+")

_REDACTING_FILTER = protect_loggers(("azure", "msal", "urllib3", "httpx", "httpcore"))


@dataclass(frozen=True)
class SpeechAccessToken:
    """A Speech STS token for the browser and its expiry in epoch seconds."""

    token: str = field(repr=False)
    expires_on: int


class SpeechTokenUnavailable(Exception):
    """No token could be issued; carries no detail of the credential chain or the exchange."""


class SpeechTokenClient(Protocol):
    async def access_token(self) -> SpeechAccessToken: ...


class EntraSpeechTokenClient:
    """Exchanges one credential's Entra token for Speech tokens; kept for the life of the
    process so the credential's cache holds."""

    def __init__(
        self,
        credential: TokenCredential,
        issue_token_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._credential = credential
        self._issue_token_url = issue_token_url
        self._transport = transport

    async def access_token(self) -> SpeechAccessToken:
        entra = await self._entra_token()
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=STS_TIMEOUT_SECONDS
            ) as http:
                response = await http.post(
                    self._issue_token_url,
                    headers={"Authorization": f"Bearer {entra}", "Content-Length": "0"},
                )
        except httpx.HTTPError as exc:
            logger.warning("speech token exchange failed: %s", type(exc).__name__)
            raise SpeechTokenUnavailable(type(exc).__name__) from None
        if response.status_code != 200:
            logger.warning("speech token exchange refused: HTTP %s", response.status_code)
            raise SpeechTokenUnavailable(f"HTTP {response.status_code}")
        token = response.text.strip()
        if len(token) > _MAX_STS_TOKEN_CHARS or not _STS_TOKEN_PATTERN.fullmatch(token):
            logger.warning("speech token exchange answered an unusable token")
            raise SpeechTokenUnavailable("unusable token")
        return SpeechAccessToken(token=token, expires_on=_expiry(token))

    async def _entra_token(self) -> str:
        """The credential is synchronous; it runs in a worker thread so the loop never blocks."""
        try:
            access = await asyncio.to_thread(self._credential.get_token, TOKEN_SCOPE)
        except Exception as exc:
            # The credential chain's messages name environment and account details.
            logger.warning("speech Entra token could not be obtained: %s", type(exc).__name__)
            raise SpeechTokenUnavailable(type(exc).__name__) from None
        return access.token


_override: list[SpeechTokenClient | None] = []
_cached: dict[tuple[str, str], SpeechTokenClient] = {}


def get_speech_token_client() -> SpeechTokenClient | None:
    """The configured client, or None when no Speech resource or credential is configured."""
    if _override:
        return _override[0]
    return _configured(get_settings())


def set_speech_token_client(client: SpeechTokenClient | None) -> None:
    """Replace the configured client (tests); `reset_speech_token_client` restores it."""
    _override[:] = [client]


def reset_speech_token_client() -> None:
    _override.clear()


def speech_configured(settings: Settings) -> bool:
    """A Speech resource and its endpoint are set, and a credential may obtain the Entra token."""
    return (
        settings.speech_resource_id is not None
        and settings.speech_endpoint is not None
        and _credential_kind(settings) is not None
    )


def issue_token_url(endpoint: str) -> str:
    """The resource's STS endpoint on its custom subdomain."""
    return endpoint.rstrip("/") + ISSUE_TOKEN_PATH


def _configured(settings: Settings) -> SpeechTokenClient | None:
    if not speech_configured(settings):
        return None
    assert settings.speech_endpoint is not None
    kind = _credential_kind(settings)
    assert kind is not None
    key = (kind, settings.speech_endpoint)
    client = _cached.get(key)
    if client is None:
        credential = _credential(settings)
        assert credential is not None
        client = EntraSpeechTokenClient(credential, issue_token_url(settings.speech_endpoint))
        _cached.clear()
        _cached[key] = client
    return client


def _credential_kind(settings: Settings) -> str | None:
    """`mi:<client id>`, `cli`, or None when no credential may obtain the Entra token."""
    if settings.speech_client_id is not None:
        return f"mi:{settings.speech_client_id}"
    if settings.is_dev and not settings.azure_federated_token_file:
        return "cli"
    return None


def _credential(settings: Settings) -> TokenCredential | None:
    kind = _credential_kind(settings)
    if kind is None:
        return None
    if kind == "cli":
        from azure.identity import AzureCliCredential

        return AzureCliCredential()
    from azure.identity import ManagedIdentityCredential

    return ManagedIdentityCredential(client_id=settings.speech_client_id)


def _expiry(token: str) -> int:
    """The token's `exp` claim, or the default lifetime from now when it cannot be read. The
    token comes straight from the resource's STS endpoint over TLS; it is not verified here."""
    fallback = int(time.time()) + DEFAULT_STS_LIFETIME_SECONDS
    parts = token.split(".")
    if len(parts) != 3:
        return fallback
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
    except (binascii.Error, ValueError, AttributeError):
        return fallback
    if isinstance(exp, int | float) and not isinstance(exp, bool) and exp > time.time():
        return int(exp)
    return fallback
