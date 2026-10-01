"""The `companyCreation` setting: read in the scene, and enforced on `POST /companies`."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant_settings import TenantSettings
from tests.conftest import Persona, TenantFixture

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def add_company(client: httpx.AsyncClient, persona: Persona) -> httpx.Response:
    return await client.post(
        "/companies",
        json={"name": f"Branch {uuid.uuid4().hex[:6]}", "start": "one_cell"},
        headers=persona.headers,
    )


async def set_company_creation(session: AsyncSession, tenant: TenantFixture, allowed: bool) -> None:
    settings = await session.get(TenantSettings, tenant.tenant_id)
    assert settings is not None
    settings.company_creation = allowed
    await session.commit()


async def test_scene_reads_company_creation_on_by_default(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    scene = await client.get("/scene", headers=tenant.owner.headers)

    assert scene.status_code == 200, scene.text
    assert scene.json()["settings"]["companyCreation"] is True


async def test_companies_cannot_be_added_while_company_creation_is_off(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    await set_company_creation(session, tenant, False)
    try:
        scene = await client.get("/scene", headers=tenant.admin.headers)
        assert scene.json()["settings"]["companyCreation"] is False

        refused = await add_company(client, tenant.admin)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "company_creation_disabled"
        # Every caller is refused the same way, before any role check.
        also_refused = await add_company(client, tenant.builder)
        assert also_refused.status_code == 409, also_refused.text
        assert also_refused.json()["code"] == "company_creation_disabled"
    finally:
        await set_company_creation(session, tenant, True)

    allowed = await add_company(client, tenant.admin)
    assert allowed.status_code == 201, allowed.text
    assert (await add_company(client, tenant.builder)).status_code == 403
