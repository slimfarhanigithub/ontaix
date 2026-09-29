"""Regression tests from the security review: budgets, failure semantics, sessions and secrets.

The real adapter runs over an in-memory HTTP transport; no network call is made."""

from __future__ import annotations

import asyncio
import functools
import io
import json
import logging
import time
import traceback
import uuid
from datetime import UTC, datetime

import anthropic
import httpx2
import pytest
from sqlalchemy import text

from app.clients import db_client
from app.clients.llm_client import (
    LlmProviderError,
    LlmTimeout,
    reset_llm_client,
)
from app.config import get_settings
from app.repositories.teach_session_turn_repository import SessionKey
from app.services import llm_usage_service, teach_extraction_service, teach_session_service
from app.services.rate_limit_service import Budget, try_charge
from app.utilities.clock import get_clock
from tests.conftest import TenantFixture
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_review_rules import C0, answer, install, intent, new, post

pytestmark = pytest.mark.asyncio(loop_scope="session")

# A made-up value, not a credential: the test checks it never leaves the adapter.
SECRET = "dummy-REVIEWDUMMY-value"


async def month_tokens(tenant_id) -> int:
    async with db_client.get_session_factory()() as s:
        v = (
            await s.execute(
                text(
                    "SELECT coalesce(sum(tokens),0) FROM ontaix.llm_month_usage WHERE tenant_id=:t"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
    return int(v)


async def calls(tenant_id) -> list[dict]:
    async with db_client.get_session_factory()() as s:
        r = await s.execute(
            text("SELECT * FROM ontaix.llm_call WHERE tenant_id=:t ORDER BY occurred_at"),
            {"t": tenant_id},
        )
        return [dict(x._mapping) for x in r]


# ---------------------------------------------------------------- budgets


async def test_rate_window_atomic_40_concurrent(tenant: TenantFixture, monkeypatch):
    monkeypatch.setenv("ONTAIX_LLM_CALLS_PER_HOUR", "10")
    get_settings.cache_clear()
    try:
        actor = uuid.uuid4()
        results = await asyncio.gather(
            *[try_charge(Budget.LLM, tenant.tenant_id, "user", actor) for _ in range(40)]
        )
    finally:
        monkeypatch.delenv("ONTAIX_LLM_CALLS_PER_HOUR")
        get_settings.cache_clear()
    assert sum(results) == 10


async def test_month_reserve_atomic_40_concurrent(tenant: TenantFixture):
    results = await asyncio.gather(
        *[llm_usage_service.reserve(tenant.tenant_id, 1000, 10_500) for _ in range(40)]
    )
    granted = sum(r is not None for r in results)
    assert granted == 10
    assert await month_tokens(tenant.tenant_id) == 10_000


@pytest.mark.parametrize(
    "outcome,make",
    [
        ("timeout", lambda: LlmTimeout("timeout")),
        ("provider_error", lambda: LlmProviderError("status", 100, 5, 0.0, 3)),
        ("provider_error", lambda: RuntimeError("boom")),
        ("invalid_output", lambda: "not json {"),
        ("invalid_output", lambda: "[" * 2_000_000),
        (
            "invalid_output",
            lambda: json.dumps({"intents": [], "unresolved": [], "x": "a" * 5_000_000}),
        ),
    ],
)
async def test_failures_degrade_and_release(client, tenant: TenantFixture, outcome, make):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    before = await month_tokens(tenant.tenant_id)
    install(lambda ctx: make())
    r = await post(client, tenant, company_id, "these services sell stuff")
    after = await month_tokens(tenant.tenant_id)
    assert r["llmOutcome"] == outcome and r["degraded"] is True
    reported = 105 if "status" in repr(make()) else 0
    assert after - before == {"timeout": 0, "provider_error": reported}.get(outcome, 876)


async def test_an_unexpected_error_reading_the_answer_still_settles_and_records(
    client, tenant: TenantFixture, monkeypatch
):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    before = await month_tokens(tenant.tenant_id)
    n_before = len(await calls(tenant.tenant_id))

    def boom(*a, **k):
        raise KeyError("unexpected")

    monkeypatch.setattr(teach_extraction_service, "_interpret", boom)
    install(lambda ctx: answer())
    r = await post(client, tenant, company_id, "these services sell stuff")
    after = await month_tokens(tenant.tenant_id)
    rows = await calls(tenant.tenant_id)
    assert r["llmOutcome"] == "invalid_output" and r["degraded"] is True
    assert after - before == 876
    assert len(rows) == n_before + 1 and rows[-1]["outcome"] == "invalid_output"


async def test_settle_to_reserved_month(client, tenant: TenantFixture):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    clock = get_clock()
    clock.freeze(datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC))
    try:

        def fn(ctx):
            clock.freeze(datetime(2026, 10, 1, 0, 0, 5, tzinfo=UTC))
            return answer(intent(C0, new("Services"), 6, 14, "sells"))

        install(fn)
        await post(client, tenant, company_id, "these services sell stuff")
    finally:
        clock.freeze(None)
    async with db_client.get_session_factory()() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT month, tokens FROM ontaix.llm_month_usage"
                    " WHERE tenant_id = :t ORDER BY month"
                ),
                {"t": tenant.tenant_id},
            )
        ).all()
    assert [(str(m), t) for m, t in rows] == [("2026-09-01", 876)]


# ---------------------------------------------------------------- sessions


async def test_turn_allocation_concurrent_and_isolation(client, tenant: TenantFixture):
    company_id = tenant.company_id
    sid = uuid.uuid4()
    key = SessionKey(tenant.tenant_id, "user", tenant.builder.user_id, company_id, sid)
    await asyncio.gather(
        *[
            teach_session_service.store_turn(key, f"sentence {i}", "rules", [], [f"L{i}"])
            for i in range(12)
        ]
    )
    async with db_client.get_session_factory()() as s:
        idx = (
            (
                await s.execute(
                    text(
                        "SELECT turn_index FROM ontaix.teach_session_turn"
                        " WHERE session_id = :s ORDER BY 1"
                    ),
                    {"s": sid},
                )
            )
            .scalars()
            .all()
        )
    assert idx == list(range(4, 12))
    await configure(tenant)
    fake = install(lambda ctx: answer())
    body = {
        "companyId": str(company_id),
        "text": "these services sell stuff",
        "sessionId": str(sid),
    }
    r = await client.post("/teach/parse", json=body, headers=tenant.owner.headers)
    assert r.status_code == 200, r.text
    assert json.loads(fake.requests[-1].user)["sessionTurns"] == []
    r = await client.post("/teach/parse", json=body, headers=tenant.builder.headers)
    assert len(json.loads(fake.requests[-1].user)["sessionTurns"]) == 8
    async with db_client.get_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.teach_session_turn"
                " SET created_at = now() - interval '2 hours 1 second',"
                " expires_at = now() - interval '1 second' WHERE session_id = :s"
            ),
            {"s": sid},
        )
        await s.commit()
    assert await teach_session_service.recent_turns(key) == []
    purged = await teach_session_service.purge_expired()
    assert purged >= 8


# ---------------------------------------------------------------- secrets and wall clock


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.buf = io.StringIO()

    def emit(self, record):
        try:
            self.buf.write(self.format(record) + "\n")
            if record.exc_info:
                self.buf.write("".join(traceback.format_exception(*record.exc_info)))
        except Exception as e:  # pragma: no cover
            self.buf.write(f"<format error {e}>\n")


def _handler_for(mode):
    seen = {}

    async def handler(request: httpx2.Request):
        seen["key"] = request.headers.get("x-api-key")
        if mode == "401":
            return httpx2.Response(
                401,
                json={
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                },
            )
        if mode == "500":
            return httpx2.Response(
                500, json={"type": "error", "error": {"type": "api_error", "message": "Internal"}}
            )
        if mode == "connect":
            raise httpx2.ConnectError("connection refused", request=request)
        if mode == "raise":
            raise RuntimeError("handler exploded")
        if mode == "slow":
            await asyncio.sleep(5)
        if mode == "badjson":
            return httpx2.Response(200, content=b"{not json")
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": "garbage not json"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )

    return handler, seen


@pytest.mark.parametrize(
    "mode", ["401", "500", "connect", "raise", "slow", "badjson", "ok_garbage"]
)
async def test_real_adapter_never_leaks_key(client, tenant: TenantFixture, monkeypatch, mode):
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    monkeypatch.setenv("ONTAIX_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ONTAIX_LLM_MODEL", "claude-sonnet-5")
    monkeypatch.setenv(
        "ONTAIX_LLM_PRICE_TABLE",
        '{"claude-sonnet-5": {"inputEurPerMTok": 1, "outputEurPerMTok": 5}}',
    )
    monkeypatch.setenv("ONTAIX_ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("ONTAIX_LLM_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    handler, seen = _handler_for(mode)
    original = anthropic.AsyncAnthropic
    monkeypatch.setattr(
        anthropic,
        "AsyncAnthropic",
        functools.partial(
            original, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        ),
    )
    import app.clients.llm_client as lc

    monkeypatch.setattr(lc, "_cached", {})
    reset_llm_client()
    cap = _Capture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(cap)
    root.setLevel(logging.DEBUG)
    for name in ("anthropic", "anthropic._base_client", "httpx2", "httpcore"):
        logging.getLogger(name).addHandler(cap)
    try:
        started = time.monotonic()
        r = await client.post(
            "/teach/parse",
            json={"companyId": str(company_id), "text": "these services sell stuff"},
            headers=tenant.builder.headers,
        )
        elapsed = time.monotonic() - started
    finally:
        root.removeHandler(cap)
        root.setLevel(old_level)
        for name in ("anthropic", "anthropic._base_client", "httpx2", "httpcore"):
            logging.getLogger(name).removeHandler(cap)
        get_settings.cache_clear()
    logs = cap.buf.getvalue()
    async with db_client.get_session_factory()() as s:
        tables = (
            (await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='ontaix'")))
            .scalars()
            .all()
        )
        hits = []
        for t in tables:
            n = (
                await s.execute(
                    text(f"SELECT count(*) FROM ontaix.{t} x WHERE x::text LIKE :k"),
                    {"k": "%REVIEWDUMMY%"},
                )
            ).scalar_one()
            if n:
                hits.append(t)
    assert r.status_code == 200
    assert "REVIEWDUMMY" not in logs and "REVIEWDUMMY" not in r.text and not hits
    if mode == "slow":
        assert elapsed < 2.0


async def test_a_transcripts_segment_turns_are_stored_together(client, tenant: TenantFixture):
    await configure(tenant, llm_monthly_token_cap=0)
    sid = uuid.uuid4()

    async def speak(tag: str) -> None:
        body = {
            "companyId": str(tenant.company_id),
            "text": f"{tag} one has parts. {tag} two has parts. {tag} three has parts.",
            "origin": "speech",
            "sessionId": str(sid),
        }
        r = await client.post("/teach/parse", json=body, headers=tenant.builder.headers)
        assert r.status_code == 200, r.text

    await asyncio.gather(speak("Alpha"), speak("Beta"))
    async with db_client.get_session_factory()() as s:
        sentences = (
            (
                await s.execute(
                    text(
                        "SELECT sentence FROM ontaix.teach_session_turn WHERE session_id = :s"
                        " ORDER BY turn_index"
                    ),
                    {"s": sid},
                )
            )
            .scalars()
            .all()
        )
    tags = [sentence.split()[0] for sentence in sentences]
    assert sorted(tags) == ["Alpha"] * 3 + ["Beta"] * 3
    assert tags in (["Alpha"] * 3 + ["Beta"] * 3, ["Beta"] * 3 + ["Alpha"] * 3)
