"""A model step that is configured but does not answer: typed text and speech draft nothing,
document sentences keep the grammar, and a step that is off keeps the grammar for every origin.

The Foundry client is real and its token cache runs over a fake credential that fails as the
Azure CLI does when it cannot be invoked; no request leaves the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx
import pytest

import app.clients.entra_token_client as entra_token_client
import app.clients.foundry_llm_client as foundry
from app.clients.entra_token_client import EntraTokenCache
from app.clients.foundry_llm_client import FoundryLlmClient
from app.clients.llm_client import LlmProviderError, set_llm_client
from app.config import ModelPrice
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure, teach
from tests.test_teach_speech import speak

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = (
    "insight is a company that has employees these employees can be consultants or from "
    "support services"
)
PRICE = ModelPrice(inputEurPerMTok=Decimal("2"), outputEurPerMTok=Decimal("10"))
LIFETIME = 3600


@dataclass
class _Token:
    token: str
    expires_on: int


class FlakyCredential:
    """Hands out one token, then fails like an Azure CLI that cannot be invoked."""

    def __init__(self, clock: list[float], tokens: int = 0) -> None:
        self.clock = clock
        self.tokens = tokens
        self.attempts = 0

    def get_token(self, *scopes: str) -> _Token:
        self.attempts += 1
        if self.tokens:
            self.tokens -= 1
            return _Token("t", int(self.clock[0]) + LIFETIME)
        raise RuntimeError("Failed to invoke the Azure CLI")


@pytest.fixture
def foundry_with(monkeypatch: pytest.MonkeyPatch):
    """Installs a Foundry client whose token cache runs over `credential`."""
    monkeypatch.setattr(entra_token_client, "RETRY_BACKOFF_SECONDS", 0.0)

    def install(credential: FlakyCredential) -> EntraTokenCache:
        cache = EntraTokenCache(
            foundry.TOKEN_SCOPE, lambda: credential, clock=lambda: credential.clock[0]
        )
        monkeypatch.setattr(foundry, "entra_token_provider", lambda: cache.token)
        client = FoundryLlmClient(
            "https://ais-ontaix-test.cognitiveservices.azure.com/", "gpt", "gpt", PRICE, "low"
        )
        set_llm_client(client)
        return cache

    return install


def assert_nothing_drafted(result: dict) -> None:
    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == (
        "rules",
        "provider_error",
        True,
    )
    assert result["outcome"] == "not_understood"
    assert result["drafts"] == [] and result["intents"] == []
    assert {u["reason"] for u in result["unresolved"]} == {"model_unavailable"}


async def test_the_owners_sentence_with_a_failing_credential_drafts_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, foundry_with
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    credential = FlakyCredential([1_000_000.0])
    foundry_with(credential)

    typed = await teach(client, tenant, company_id, OWNER)
    spoken = await speak(client, tenant, company_id, OWNER)

    assert_nothing_drafted(typed)
    assert typed["unresolved"] == [{"text": OWNER, "reason": "model_unavailable"}]
    assert_nothing_drafted(spoken)
    # Each call tried the credential twice.
    assert credential.attempts == 4


async def test_an_expired_token_and_a_failing_credential_draft_nothing(
    client: httpx.AsyncClient, tenant: TenantFixture, foundry_with
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    clock = [1_000_000.0]
    credential = FlakyCredential(clock, tokens=1)
    cache = foundry_with(credential)
    assert await cache.token() == "t"

    clock[0] += LIFETIME + 1
    typed = await teach(client, tenant, company_id, "A plant has machines")
    spoken = await speak(client, tenant, company_id, "A plant has machines.")

    assert_nothing_drafted(typed)
    assert_nothing_drafted(spoken)


async def test_a_document_sentence_keeps_the_grammar_when_the_model_does_not_answer(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    await configure(tenant)
    sentence = "A plant has machines."
    upload = await client.post(
        "/import/sentences",
        files={"file": ("brief.txt", sentence.encode(), "text/plain")},
        headers=tenant.builder.headers,
    )
    assert upload.status_code == 200, upload.text
    import_ref = {"importId": upload.json()["importId"], "sentenceIndex": 0}
    fake_llm.answer(LlmProviderError("credential"))

    result = await teach(client, tenant, tenant.company_id, import_ref=import_ref)

    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == (
        "rules",
        "provider_error",
        True,
    )
    assert [d["label"] for d in result["drafts"]] == ["Plant", "Machine"]
    assert result["unresolved"] == [{"text": sentence, "reason": "model_unavailable"}]


async def test_with_no_model_configured_typed_and_spoken_text_keep_the_grammar(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    await configure(tenant)
    set_llm_client(None)

    typed = await teach(client, tenant, tenant.company_id, "A plant has machines")
    spoken = await speak(client, tenant, tenant.company_id, "A plant has machines.")

    assert (typed["llmOutcome"], spoken["llmOutcome"]) == ("not_triggered", "not_configured")
    for result in (typed, spoken):
        assert [d["label"] for d in result["drafts"]] == ["Plant", "Machine"]
