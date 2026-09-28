"""The request transaction commits before the response is sent, and audit filters are validated."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.storage.concept import Concept
from tests.conftest import TenantFixture
from tests.test_proposals import approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def tolerant_client(migrated_database: str) -> AsyncIterator[httpx.AsyncClient]:
    """A client that receives the application's 500 response instead of the raised exception."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def test_failing_commit_answers_5xx_not_2xx(
    tolerant_client: httpx.AsyncClient,
    tenant: TenantFixture,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    response = await propose_concept(
        tolerant_client, tenant, tenant.builder, "Unsaved", tenant.root_id
    )
    monkeypatch.undo()

    assert response.status_code >= 500, response.text
    stored = await session.scalar(
        select(Concept).where(Concept.tenant_id == tenant.tenant_id, Concept.label == "Unsaved")
    )
    assert stored is None


@pytest.mark.parametrize(
    "bound", ["2020-01-01T00:00:00", "2020-01-01", "not a time", "2020-13-01T00:00:00+00:00"]
)
async def test_audit_time_filter_without_offset_is_a_bad_request(
    client: httpx.AsyncClient, tenant: TenantFixture, bound: str
) -> None:
    await approved(client, tenant, "Audited")

    response = await client.get(
        "/audit", params={"filter[from]": bound}, headers=tenant.governor.headers
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "bad_request"


async def test_audit_time_filter_with_offset_filters_entries(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    await approved(client, tenant, "Audited")

    since = await client.get(
        "/audit",
        params={"filter[from]": "2020-01-01T00:00:00+00:00"},
        headers=tenant.governor.headers,
    )
    until = await client.get(
        "/audit",
        params={"filter[to]": "2020-01-01T00:00:00Z"},
        headers=tenant.governor.headers,
    )

    assert since.status_code == 200, since.text
    assert since.json()["total"] >= 1
    assert until.status_code == 200, until.text
    assert until.json()["total"] == 0
