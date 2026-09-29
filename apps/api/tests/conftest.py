"""Test fixtures: a real PostgreSQL, the migrated schema, the app client and dev callers.

`ONTAIX_TEST_DATABASE_URL` points at a PostgreSQL 16 server (CI). When it is unset an embedded
server from the `pgserver` package starts in a temporary directory for the session.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import db_client
from app.clients.llm_client import reset_llm_client, set_llm_client
from app.clients.ocr_client import reset_ocr_client, set_ocr_client
from app.config import get_settings
from app.main import app
from app.migrations.runner import upgrade_to_head
from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.services import company_service
from app.services.ontology_view_service import load_view
from tests.llm_fakes import FakeLlmClient

DEV_ISSUER = "dev"


@dataclass(frozen=True)
class Persona:
    """A seeded user of a test tenant, addressed by its dev subject."""

    subject: str
    user_id: uuid.UUID

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Ontaix-User": self.subject}


@dataclass(frozen=True)
class TenantFixture:
    tenant_id: uuid.UUID
    slug: str
    company_id: uuid.UUID
    company_name: str
    root_id: uuid.UUID
    builder: Persona
    owner: Persona
    governor: Persona
    second_governor: Persona
    admin: Persona
    outsider: Persona


def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> dict[str, object]:
    """psycopg's async driver needs a selector loop; Windows defaults to the proactor loop."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


@pytest.fixture(autouse=True)
def no_language_model(request: pytest.FixtureRequest) -> Iterator[None]:
    """No test reaches a model or OCR provider unless it is marked `live`."""
    if request.node.get_closest_marker("live") is None:
        set_llm_client(None)
        set_ocr_client(None)
    try:
        yield
    finally:
        reset_llm_client()
        reset_ocr_client()


@pytest.fixture
def fake_llm() -> FakeLlmClient:
    """A model client answering from recorded fixtures, installed for one test."""
    client = FakeLlmClient()
    set_llm_client(client)
    return client


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    configured = os.environ.get("ONTAIX_TEST_DATABASE_URL")
    if configured:
        yield configured
        return
    import pgserver

    pgdata = Path(tempfile.mkdtemp(prefix="ontaix-pg-")) / "pgdata"
    server = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    os.environ["ONTAIX_ENVIRONMENT"] = "dev"
    os.environ["ONTAIX_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    upgrade_to_head(database_url)
    db_client.configure_engine(database_url)
    return database_url


@pytest_asyncio.fixture(loop_scope="session")
async def session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    async with db_client.get_session_factory()() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def client(migrated_database: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def tenant(migrated_database: str) -> TenantFixture:
    """A fresh tenant with one home company and one user per role."""
    slug = f"t-{uuid.uuid4().hex[:10]}"
    async with db_client.get_session_factory()() as s:
        t = await tenant_repository.create(s, slug, f"Tenant {slug}")
        await tenant_settings_repository.create(s, t.id)
        await view_state_repository.create(s, t.id)
        personas: dict[str, Persona] = {}
        for role in ("builder", "owner", "governor", "second_governor", "admin", "outsider"):
            subject = f"{role}@{slug}.test"
            user = await app_user_repository.create(
                s,
                tenant_id=t.id,
                issuer=DEV_ISSUER,
                subject=subject,
                email=subject,
                name=role.replace("_", " ").title(),
                department=None,
                company_id=None,
            )
            personas[role] = Persona(subject=subject, user_id=user.id)
        view = await load_view(s, t.id)
        company = await company_service.add_company(
            s, view, f"Home {slug}", "one line of context", is_home=True
        )
        root = view.root_of(company.id)
        assert root is not None
        grants = {
            "builder": (RoleName.BUILDER, ScopeKind.TENANT),
            "owner": (RoleName.OWNER, ScopeKind.COMPANY),
            "governor": (RoleName.GOVERNOR, ScopeKind.TENANT),
            "second_governor": (RoleName.GOVERNOR, ScopeKind.TENANT),
            "admin": (RoleName.ADMINISTRATOR, ScopeKind.TENANT),
        }
        for role, (role_name, scope_kind) in grants.items():
            group = await user_group_repository.create(s, t.id, f"{role} group", "")
            await group_member_repository.add(s, t.id, group.id, personas[role].user_id)
            await group_role_repository.create(
                s,
                tenant_id=t.id,
                group_id=group.id,
                role=role_name,
                scope_kind=scope_kind,
                scope_company_id=company.id if scope_kind is ScopeKind.COMPANY else None,
                scope_domain_key=None,
            )
        await s.commit()
        return TenantFixture(
            tenant_id=t.id,
            slug=slug,
            company_id=company.id,
            company_name=company.name,
            root_id=root.id,
            builder=personas["builder"],
            owner=personas["owner"],
            governor=personas["governor"],
            second_governor=personas["second_governor"],
            admin=personas["admin"],
            outsider=personas["outsider"],
        )
