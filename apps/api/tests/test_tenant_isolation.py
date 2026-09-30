"""Two organizations, A and B: a signed-in member of A never sees, reads or changes B's data,
through any endpoint the API serves, and row-level security holds under the repositories.

The endpoint sweeps enumerate the application's own routes, so an endpoint added later is
covered without editing this file. The database tests run as the application role itself.
"""

from __future__ import annotations

import ast
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.clients import db_client
from app.main import API_PREFIX, app
from tests.auth_helpers import create_member, group_ids, ready_member, signed_in
from tests.conftest import AccountFixture, Browser, TenantFixture, make_tenant

EXCLUDED_PREFIXES = (f"{API_PREFIX}/auth", f"{API_PREFIX}/admin", f"{API_PREFIX}/healthz")
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
# Modules that may use the platform role: sign-in, the platform portal, the admin CLI,
# cross-organization purges, the extraction runner's claim, and the dev header lookup.
PLATFORM_ROLE_MODULES = {
    "app/auth.py",
    "app/clients/db_client.py",
    "app/seed/__main__.py",
    "app/services/auth_upkeep_service.py",
    "app/services/concept_expansion_service.py",
    "app/services/document_extraction_runner_service.py",
    "app/services/document_extraction_service.py",
    "app/services/import_purge_service.py",
    "app/services/llm_usage_service.py",
    "app/services/rate_limit_service.py",
    "app/services/teach_session_service.py",
}
PLATFORM_NAMES = {"platform_session", "get_platform_session_factory", "platform_session_dependency"}


@dataclass(frozen=True)
class OrganizationB:
    tenant: TenantFixture
    proposal_id: str
    concept_id: str
    domain_product_id: str
    markers: tuple[str, ...]


@pytest_asyncio.fixture(loop_scope="session")
async def member_a(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> tuple[Browser, TenantFixture]:
    """A signed-in member of organization A holding Administrator, Governor and Builder."""
    a = await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    groups = await group_ids(
        admin, str(a.tenant_id), "admin group", "governor group", "builder group"
    )
    member = await create_member(admin, a.tenant_id, groups)
    browser, _ = await ready_member(browsers(), member)
    return browser, a


@pytest_asyncio.fixture(loop_scope="session")
async def organization_b(client: httpx.AsyncClient) -> OrganizationB:
    """Organization B with a company, its root and a pending proposal of a new concept."""
    b = await make_tenant()
    proposed = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(b.company_id),
            "parentId": str(b.root_id),
            "label": "Secret Formula",
            "domainKey": "production",
            "action": "operates",
        },
        headers=b.builder.headers,
    )
    assert proposed.status_code == 202, proposed.text
    products = await client.get("/domain-products", headers=b.governor.headers)
    return OrganizationB(
        tenant=b,
        proposal_id=proposed.json()["id"],
        concept_id=str(b.root_id),
        domain_product_id=products.json()[0]["id"],
        markers=(
            str(b.tenant_id),
            str(b.company_id),
            str(b.root_id),
            proposed.json()["id"],
            b.company_name,
            "Secret Formula",
            b.slug,
        ),
    )


@dataclass(frozen=True)
class Route:
    path: str
    methods: set[str]


def organization_routes() -> list[Route]:
    """Every organization endpoint the application serves, from its own OpenAPI document."""
    paths = app.openapi()["paths"]
    return [
        Route(path=path, methods={m.upper() for m in operations})
        for path, operations in paths.items()
        if path.startswith(API_PREFIX) and not path.startswith(EXCLUDED_PREFIXES)
    ]


def b_path(route: Route, b: OrganizationB) -> str:
    ids = {
        "company_id": str(b.tenant.company_id),
        "concept_id": b.concept_id,
        "proposal_id": b.proposal_id,
        "domain_product_id": b.domain_product_id,
    }
    path = route.path[len(API_PREFIX) :]
    return re.sub(r"\{(\w+)\}", lambda m: ids.get(m.group(1), str(uuid.uuid4())), path)


def b_bodies(b: OrganizationB) -> list[dict[str, Any]]:
    company, root = str(b.tenant.company_id), b.concept_id
    return [
        {},
        {
            "type": "concept",
            "companyId": company,
            "parentId": root,
            "label": "Leak",
            "domainKey": "production",
            "action": "leaks",
        },
        {"type": "relation", "aId": root, "bId": root, "action": "leaks"},
        {"aId": root, "bId": root},
        {"companyId": company, "text": "Secret Formula has leak"},
        {"companyId": company},
        {"name": "Leak Co", "sub": "leak", "start": "one_cell"},
        {"label": "Leaked"},
        {"hidden": True},
        {"indexes": [0]},
    ]


async def b_snapshot(b: OrganizationB) -> dict[str, Any]:
    """Every row count of B, read on the platform role, to compare before and after."""
    tables = await _tenant_tables()
    async with db_client.platform_session() as s:
        counts = {
            t: (
                await s.execute(
                    text(f"SELECT count(*) FROM ontaix.{t} WHERE tenant_id = :t"),
                    {"t": b.tenant.tenant_id},
                )
            ).scalar_one()
            for t in tables
        }
        counts["proposal_state"] = (
            await s.execute(
                text("SELECT state::text FROM ontaix.proposal WHERE id = :p"), {"p": b.proposal_id}
            )
        ).scalar_one()
        counts["company_name"] = (
            await s.execute(
                text("SELECT name FROM ontaix.company WHERE id = :c"), {"c": b.tenant.company_id}
            )
        ).scalar_one()
    return counts


async def test_every_list_and_read_of_a_shows_nothing_of_b(
    member_a: tuple[Browser, TenantFixture], organization_b: OrganizationB
) -> None:
    browser, a = member_a
    swept = 0
    for route in organization_routes():
        if "GET" not in route.methods or "{" in route.path:
            continue
        response = await browser.call("GET", route.path[len(API_PREFIX) :])
        swept += 1
        assert response.status_code < 500, (route.path, response.text)
        for marker in organization_b.markers:
            assert marker not in response.text, (route.path, marker)
    assert swept >= 8
    scene = (await browser.call("GET", "/scene")).json()
    assert [c["id"] for c in scene["companies"]] == [str(a.company_id)]


async def test_every_read_by_id_of_b_is_not_found(
    member_a: tuple[Browser, TenantFixture], organization_b: OrganizationB
) -> None:
    browser, _ = member_a
    swept = 0
    for route in organization_routes():
        if "GET" not in route.methods or "{" not in route.path:
            continue
        response = await browser.call("GET", b_path(route, organization_b))
        swept += 1
        assert response.status_code in (403, 404, 410), (route.path, response.status_code)
        for marker in organization_b.markers[4:]:
            assert marker not in response.text, (route.path, marker)
    assert swept >= 6


async def test_no_write_of_a_changes_b(
    member_a: tuple[Browser, TenantFixture], organization_b: OrganizationB
) -> None:
    browser, _ = member_a
    before = await b_snapshot(organization_b)
    swept = 0
    for route in organization_routes():
        for method in route.methods - {"GET", "HEAD"}:
            for body in b_bodies(organization_b):
                response = await browser.call(method, b_path(route, organization_b), json=body)
                swept += 1
                # 503 is the speech token's answer when no Speech resource is configured.
                assert response.status_code < 500 or response.status_code == 503, (
                    method,
                    route.path,
                    response.text,
                )
                if "{" in route.path:
                    assert response.status_code >= 400, (method, route.path, response.text)
                for marker in organization_b.markers[4:]:
                    assert marker not in response.text, (method, route.path, marker)
    assert swept >= 100
    assert await b_snapshot(organization_b) == before


async def test_the_dev_header_of_a_reads_nothing_of_b(
    client: httpx.AsyncClient, tenant: TenantFixture, organization_b: OrganizationB
) -> None:
    for path in ("/scene", "/companies", "/proposals", "/concepts", "/audit"):
        response = await client.get(path, headers=tenant.admin.headers)
        for marker in organization_b.markers:
            assert marker not in response.text, (path, marker)
    response = await client.get(
        f"/proposals/{organization_b.proposal_id}", headers=tenant.admin.headers
    )
    assert response.status_code == 404


async def test_row_level_security_fails_closed_without_an_organization(
    organization_b: OrganizationB,
) -> None:
    tables = await _tenant_tables()
    async with db_client.get_session_factory()() as s:
        for table in [*tables, "tenant"]:
            count = (await s.execute(text(f"SELECT count(*) FROM ontaix.{table}"))).scalar_one()
            assert count == 0, table


async def test_row_level_security_confines_the_application_role_to_one_organization(
    tenant: TenantFixture, organization_b: OrganizationB
) -> None:
    b = organization_b.tenant
    tables = await _tenant_tables()
    async with db_client.tenant_session(tenant.tenant_id) as s:
        for table in tables:
            foreign = (
                await s.execute(
                    text(f"SELECT count(*) FROM ontaix.{table} WHERE tenant_id <> :a"),
                    {"a": tenant.tenant_id},
                )
            ).scalar_one()
            assert foreign == 0, table
        tenants = (await s.execute(text("SELECT id FROM ontaix.tenant"))).scalars().all()
        assert tenants == [tenant.tenant_id]
        changed = await s.execute(
            text("UPDATE ontaix.company SET name = 'Hijacked' WHERE tenant_id = :b"),
            {"b": b.tenant_id},
        )
        assert changed.rowcount == 0
        await s.rollback()
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db_client.tenant_session(tenant.tenant_id) as s:
            await s.execute(
                text("INSERT INTO ontaix.user_group (tenant_id, name) VALUES (:b, 'Intruders')"),
                {"b": b.tenant_id},
            )


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT count(*) FROM ontaix.account",
        "SELECT count(*) FROM ontaix.auth_session",
        "SELECT count(*) FROM ontaix.password_credential",
        "SELECT count(*) FROM ontaix.sign_in_throttle",
        "SELECT count(*) FROM ontaix.platform_audit_entry",
        "UPDATE ontaix.organization_settings SET company_mode = 'multiple'",
        "UPDATE ontaix.tenant SET disabled_at = NULL",
    ],
)
async def test_the_application_role_cannot_touch_sign_in_or_platform_tables(
    tenant: TenantFixture, statement: str
) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db_client.tenant_session(tenant.tenant_id) as s:
            await s.execute(text(statement))


def test_only_the_listed_modules_use_the_platform_role() -> None:
    """Every other module reaches the database through a session bound to an organization."""
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        relative = path.relative_to(APP_ROOT.parent).as_posix()
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Name | ast.Attribute)
        }
        if names & PLATFORM_NAMES and relative not in PLATFORM_ROLE_MODULES:
            offenders.append(relative)
    assert offenders == []


def test_no_module_opens_an_unbound_application_session() -> None:
    """An application session is opened only bound to an organization (`tenant_session`) or by
    the request dependency, which the caller dependency binds; `auth.py` resolves the cookie in
    one unbound transaction that reads nothing but `resolve_session()`."""
    offenders = [
        path.relative_to(APP_ROOT.parent).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if "get_session_factory()()" in path.read_text(encoding="utf-8")
        and path.relative_to(APP_ROOT.parent).as_posix()
        not in {"app/auth.py", "app/clients/db_client.py"}
    ]
    assert offenders == []


async def _tenant_tables() -> list[str]:
    async with db_client.platform_session() as s:
        rows = await s.execute(
            text(
                "SELECT c.relname FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id'"
                " WHERE n.nspname = 'ontaix' AND c.relkind = 'r' AND c.relname <> 'account'"
                " ORDER BY 1"
            )
        )
        return list(rows.scalars())
