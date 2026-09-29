"""Microsoft Entra access tokens for Azure AI Speech, minted keyless for the browser's recogniser.

The token is for `https://cognitiveservices.azure.com/.default`, which every Azure AI services
resource accepts where the token's identity holds a role. It is therefore minted only by a
dedicated user-assigned managed identity that holds only Cognitive Services Speech User on the one
Speech resource: `ManagedIdentityCredential` with that identity's client id, which in the cluster
exchanges the pod's projected service account token (Kubernetes workload identity). The API's own
identity and a developer's `az login` session never mint one, in any environment; without the
dedicated identity no client exists. The credential caches its token until it nears expiry.
Tokens are never logged: the Azure and MSAL loggers are held at WARNING and filtered, and a
failure keeps only its exception type.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from azure.core.credentials import TokenCredential

from app.clients.llm_log_redaction import protect_loggers
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

_REDACTING_FILTER = protect_loggers(("azure", "msal", "urllib3"))


@dataclass(frozen=True)
class SpeechAccessToken:
    """An Entra access token for the Speech resource and its expiry in epoch seconds."""

    token: str = field(repr=False)
    expires_on: int


class SpeechTokenUnavailable(Exception):
    """No token could be minted; carries no detail of the credential chain."""


class SpeechTokenClient(Protocol):
    async def access_token(self) -> SpeechAccessToken: ...


class EntraSpeechTokenClient:
    """Mints tokens with one credential, kept for the life of the process so its cache holds."""

    def __init__(self, credential: TokenCredential) -> None:
        self._credential = credential

    async def access_token(self) -> SpeechAccessToken:
        """The credential is synchronous; it runs in a worker thread so the loop never blocks."""
        try:
            access = await asyncio.to_thread(self._credential.get_token, TOKEN_SCOPE)
        except Exception as exc:
            # The credential chain's messages name environment and account details.
            logger.warning("speech token could not be minted: %s", type(exc).__name__)
            raise SpeechTokenUnavailable(type(exc).__name__) from None
        return SpeechAccessToken(token=access.token, expires_on=int(access.expires_on))


_override: list[SpeechTokenClient | None] = []
_cached: dict[str, SpeechTokenClient] = {}


def get_speech_token_client() -> SpeechTokenClient | None:
    """The configured client, or None when no Speech resource or identity is configured."""
    if _override:
        return _override[0]
    return _configured(get_settings())


def set_speech_token_client(client: SpeechTokenClient | None) -> None:
    """Replace the configured client (tests); `reset_speech_token_client` restores it."""
    _override[:] = [client]


def reset_speech_token_client() -> None:
    _override.clear()


def speech_configured(settings: Settings) -> bool:
    """A Speech resource, its endpoint and the dedicated minting identity are all set."""
    return (
        settings.speech_resource_id is not None
        and settings.speech_endpoint is not None
        and settings.speech_client_id is not None
    )


def _configured(settings: Settings) -> SpeechTokenClient | None:
    if not speech_configured(settings):
        return None
    assert settings.speech_client_id is not None
    client = _cached.get(settings.speech_client_id)
    if client is None:
        client = EntraSpeechTokenClient(_credential(settings.speech_client_id))
        _cached.clear()
        _cached[settings.speech_client_id] = client
    return client


def _credential(client_id: str) -> TokenCredential:
    from azure.identity import ManagedIdentityCredential

    return ManagedIdentityCredential(client_id=client_id)
