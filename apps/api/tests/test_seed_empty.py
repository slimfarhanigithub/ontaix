"""The empty seed: the demo tenant with its directory and no company, in a database of its own.

The seed's users have fixed subjects, unique across tenants, so the empty tenant cannot live in
the shared test database next to the fixture tenant; this module migrates a separate database on
the same server and points the API at it for its tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import psycopg
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.clients import db_client
from app.migrations.runner import upgrade_to_head
from app.models.storage.app_user import AppUser
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.user_group import UserGroup
from app.seed import directory
from app.services.seed_service import seed_empty_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")

DEMO_HEADERS = {"X-Ontaix-User": "demo@northwind.com"}


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def empty_seeded(migrated_database: str) -> AsyncIterator[bool]:
    """A fresh database holding only the empty demo tenant; the shared one is restored after."""
    name = f"ontaix_empty_{uuid.uuid4().hex[:10]}"
    server = make_url(migrated_database)
    admin_url = server.set(drivername="postgresql").render_as_string(hide_password=False)
    url = server.set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        upgrade_to_head(url)
        await db_client.dispose_engine()
        db_client.configure_engine(url)
        async with db_client.get_platform_session_factory()() as s:
            created = await seed_empty_tenant(s)
            await s.commit()
        async with db_client.get_platform_session_factory()() as s:
            assert await seed_empty_tenant(s) is False
        yield created
    finally:
        await db_client.dispose_engine()
        db_client.configure_engine(migrated_database)
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


async def test_the_empty_seed_holds_the_directory_and_no_company(empty_seeded: bool) -> None:
    assert empty_seeded is True
    async with db_client.get_platform_session_factory()() as s:

        async def count(model: type) -> int:
            return await s.scalar(select(func.count()).select_from(model)) or 0

        assert await count(AppUser) == len(directory.USERS)
        assert await count(UserGroup) == len(directory.GROUPS)
        assert await count(Company) == 0
        assert await count(Concept) == 0
        assert await count(Proposal) == 0


async def test_the_scene_of_an_empty_tenant_has_no_company(
    client: httpx.AsyncClient, empty_seeded: bool
) -> None:
    response = await client.get("/scene", headers=DEMO_HEADERS)

    assert response.status_code == 200, response.text
    scene = response.json()
    assert (scene["companies"], scene["nodes"], scene["links"], scene["proposals"]) == (
        [],
        [],
        [],
        [],
    )
    assert len(scene["connectors"]) > 0
    assert len(scene["appearance"]["colors"]) == 9


async def test_the_first_company_of_an_empty_tenant_becomes_its_home(
    client: httpx.AsyncClient, empty_seeded: bool
) -> None:
    first = await client.post(
        "/companies",
        json={"name": "Contoso", "sub": "my company", "start": "one_cell"},
        headers=DEMO_HEADERS,
    )
    second = await client.post(
        "/companies",
        json={"name": "Fabrikam", "sub": "an acquisition", "start": "one_cell"},
        headers=DEMO_HEADERS,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["company"]["isHome"] is True
    assert second.json()["company"]["isHome"] is False
    scene = (await client.get("/scene", headers=DEMO_HEADERS)).json()
    assert [(c["name"], c["isHome"]) for c in scene["companies"]] == [
        ("Contoso", True),
        ("Fabrikam", False),
    ]
    home_id = first.json()["company"]["id"]
    removal = await client.delete(f"/companies/{home_id}", headers=DEMO_HEADERS)
    assert removal.status_code == 409, removal.text
    assert removal.json()["code"] == "home_company"
