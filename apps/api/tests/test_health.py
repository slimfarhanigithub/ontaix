"""Tests for the liveness endpoint."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio(loop_scope="session")
async def test_healthz_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
