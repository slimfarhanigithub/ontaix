"""Test fixtures: a real PostgreSQL, the migrated schema, the app client and dev callers.

`ONTAIX_TEST_DATABASE_URL` points at a PostgreSQL 16 server (CI). When it is unset an embedded
server from the `pgserver` package starts in a temporary directory for the session.

Requests run as the database role `ontaix_app`, confined by row-level security to the caller's
organization. Fixtures that build or inspect data across organizations use the platform role.
The dev identity header is on (`ONTAIX_DEV_IDENTITY_HEADER`), and `https://test` is the one
allowed origin for cookie-authenticated writes.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import SESSION_COOKIE
from app.clients import db_client
from app.clients.llm_client import reset_llm_client, set_llm_client
from app.clients.ocr_client import reset_ocr_client, set_ocr_client
from app.config import get_settings
from app.main import app
from app.migrations.runner import upgrade_to_head
from app.models.storage.base import CompanyMode, RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    organization_settings_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.services import company_service, super_admin_service
from app.services.ontology_view_service import load_view
from tests.llm_fakes import FakeLlmClient

DEV_ISSUER = "dev"
TEST_ORIGIN = "https://test"


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
    os.environ["ONTAIX_DEV_IDENTITY_HEADER"] = "true"
    os.environ["ONTAIX_ALLOWED_ORIGINS"] = f'["{TEST_ORIGIN}"]'
    os.environ["ONTAIX_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    upgrade_to_head(database_url)
    db_client.configure_engine(database_url)
    return database_url


@pytest_asyncio.fixture(loop_scope="session")
async def session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    async with db_client.get_platform_session_factory()() as s:
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
    return await make_tenant()


async def make_tenant() -> TenantFixture:
    """A fresh tenant (an organization) with one home company and one dev user per role."""
    slug = f"t-{uuid.uuid4().hex[:10]}"
    async with db_client.get_platform_session_factory()() as s:
        t = await tenant_repository.create(s, slug, f"Tenant {slug}")
        await tenant_settings_repository.create(s, t.id)
        await organization_settings_repository.create(s, t.id, CompanyMode.MULTIPLE)
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


def generated_password() -> str:
    """A fresh random password for one test: never a literal, never reused."""
    return secrets.token_urlsafe(18)


@dataclass
class Browser:
    """One browser: its own cookie jar, and the CSRF token of its current session. Unsafe
    requests carry `Origin` and `X-CSRF-Token` as the Studio sends them."""

    client: httpx.AsyncClient
    csrf: str | None = None

    async def sign_in(self, email: str, password: str) -> httpx.Response:
        response = await self.client.post(
            "/auth/sign-in",
            json={"email": email, "password": password},
            headers={"Origin": TEST_ORIGIN},
        )
        if response.status_code == 200:
            self.csrf = response.json()["csrfToken"]
        return response

    async def call(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})  # type: ignore[arg-type]
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            headers.setdefault("Origin", TEST_ORIGIN)
            if self.csrf:
                headers.setdefault("X-CSRF-Token", self.csrf)
        response = await self.client.request(method, url, headers=headers, **kwargs)  # type: ignore[arg-type]
        if response.status_code == 200 and "csrfToken" in response.text[:2000]:
            body = response.json()
            if isinstance(body, dict) and "csrfToken" in body:
                self.csrf = body["csrfToken"]
        return response

    def cookie(self) -> str | None:
        return self.client.cookies.get(SESSION_COOKIE)


@dataclass(frozen=True)
class AccountFixture:
    email: str
    password: str
    account_id: uuid.UUID


@pytest_asyncio.fixture(loop_scope="session")
async def browsers(migrated_database: str) -> AsyncIterator[Callable[[], Browser]]:
    """Opens fresh browsers on https://test (the session cookie is `Secure`), each from its own
    client IP, so one test's failed sign-ins never lock another's address."""
    opened: list[httpx.AsyncClient] = []

    def open_browser() -> Browser:
        address = ".".join(str(b) for b in secrets.token_bytes(3))
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(f"10.{address}", 50000)),
            base_url=f"{TEST_ORIGIN}/api/v1",
        )
        opened.append(client)
        return Browser(client)

    yield open_browser
    for client in opened:
        await client.aclose()


async def run_as_owner[T](operation: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run on the schema owner's login, as the admin CLI does, and commit."""
    engine = create_async_engine(
        db_client.async_database_url(get_settings().database_url or ""), hide_parameters=True
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            result = await operation(s)
            await s.commit()
            return result
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def super_admin(migrated_database: str) -> AccountFixture:
    """A fresh super admin, created as `python -m app.admin create-super-admin` does."""
    email = f"root-{uuid.uuid4().hex[:8]}@platform.test"
    password = generated_password()
    account_id = await run_as_owner(
        lambda s: super_admin_service.create_super_admin(s, email, password)
    )
    return AccountFixture(email=email, password=password, account_id=account_id)
