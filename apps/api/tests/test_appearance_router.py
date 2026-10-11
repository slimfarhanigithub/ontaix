"""`/appearance`: the read, the immediate audited change of domain colours, accent and source
colour, and the reset to the design system's defaults."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant_settings import TenantSettings
from tests.conftest import TenantFixture, make_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")

DEFAULT_ACCENT = "#d30c55"
DEFAULT_SOURCE = "#d6bd8a"


async def audit_texts(client: httpx.AsyncClient, tenant: TenantFixture) -> list[str]:
    response = await client.get("/audit?pageSize=200&kind=appearance", headers=tenant.admin.headers)
    assert response.status_code == 200, response.text
    return [e["what"] for e in response.json()["items"]]


async def test_appearance_is_read_by_any_role_with_the_defaults(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.get("/appearance", headers=tenant.builder.headers)
    scene = await client.get("/scene", headers=tenant.builder.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == scene.json()["appearance"]
    assert body["defaults"]["accent"] == DEFAULT_ACCENT
    assert body["defaults"]["source"] == DEFAULT_SOURCE
    assert set(body["colors"]) == set(body["defaults"]["colors"])
    assert "sales" in body["colors"]
    assert (await client.get("/appearance", headers=tenant.outsider.headers)).status_code == 403


async def test_administrator_changes_colours_accent_and_source_with_audit(
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()

    response = await client.patch(
        "/appearance",
        json={"colors": {"sales": "#123456"}, "accent": "#abcdef", "source": "#fedcba"},
        headers=tenant.admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["colors"]["sales"] == "#123456"
    assert body["accent"] == "#abcdef"
    assert body["source"] == "#fedcba"
    assert body["defaults"]["colors"]["sales"] != "#123456"
    assert (await client.get("/appearance", headers=tenant.admin.headers)).json() == body
    domains = (await client.get("/domains", headers=tenant.admin.headers)).json()
    assert next(d for d in domains if d["key"] == "sales")["color"] == "#123456"
    texts = await audit_texts(client, tenant)
    assert "Sales colour set to #123456" in texts
    assert "accent set to #abcdef" in texts
    assert "source colour set to #fedcba" in texts

    # The override of one domain leaves the others on their defaults.
    assert body["colors"]["supply"] == body["defaults"]["colors"]["supply"]


async def test_other_roles_cannot_change_or_reset_appearance(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    for persona in (tenant.builder, tenant.governor, tenant.owner, tenant.outsider):
        patched = await client.patch(
            "/appearance", json={"accent": "#000000"}, headers=persona.headers
        )
        reset = await client.post("/appearance/reset", headers=persona.headers)
        assert patched.status_code == 403, patched.text
        assert reset.status_code == 403, reset.text
    read = await client.get("/appearance", headers=tenant.admin.headers)
    assert read.json()["accent"] != "#000000"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"accent": "#ABCDEF"},
        {"accent": "red"},
        {"source": "#12345"},
        {"colors": {"sales": "#12345g"}},
        {"colors": {"no_such_domain": "#123456"}},
        {"theme": "dark"},
    ],
)
async def test_invalid_appearance_bodies_are_refused(
    client: httpx.AsyncClient, tenant: TenantFixture, body: dict
) -> None:
    response = await client.patch("/appearance", json=body, headers=tenant.admin.headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_failed"


async def test_a_change_in_one_tenant_leaves_the_other_untouched(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    a, b = await make_tenant(), await make_tenant()

    response = await client.patch(
        "/appearance",
        json={"colors": {"finance": "#111111"}, "accent": "#222222"},
        headers=a.admin.headers,
    )

    assert response.status_code == 200, response.text
    b_settings = await session.get(TenantSettings, b.tenant_id, populate_existing=True)
    assert b_settings is not None
    assert b_settings.accent == DEFAULT_ACCENT
    assert not b_settings.colors
    b_read = (await client.get("/appearance", headers=b.admin.headers)).json()
    assert b_read["accent"] == DEFAULT_ACCENT
    assert b_read["colors"]["finance"] == b_read["defaults"]["colors"]["finance"]


async def test_reset_returns_to_the_design_system_defaults(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    tenant = await make_tenant()
    changed = await client.patch(
        "/appearance",
        json={"colors": {"sales": "#123456", "people": "#654321"}, "accent": "#abcdef"},
        headers=tenant.admin.headers,
    )
    assert changed.status_code == 200, changed.text

    response = await client.post("/appearance/reset", headers=tenant.admin.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accent"] == DEFAULT_ACCENT
    assert body["source"] == DEFAULT_SOURCE
    assert body["colors"] == body["defaults"]["colors"]
    assert body["defaults"] == {
        "colors": body["colors"],
        "accent": DEFAULT_ACCENT,
        "source": DEFAULT_SOURCE,
    }
    stored = await session.get(TenantSettings, tenant.tenant_id, populate_existing=True)
    assert stored is not None
    assert stored.colors == {} and stored.accent == DEFAULT_ACCENT
    assert stored.source_colour == DEFAULT_SOURCE
    assert "colours reset" in await audit_texts(client, tenant)
