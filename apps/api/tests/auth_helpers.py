"""Helpers for sign-in tests: organizations and member accounts made through the platform API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.clients import db_client
from tests.conftest import AccountFixture, Browser, generated_password


@dataclass(frozen=True)
class Member:
    email: str
    password: str
    user_id: uuid.UUID
    account_id: uuid.UUID


async def signed_in(browser: Browser, account: AccountFixture | Member) -> Browser:
    response = await browser.sign_in(account.email, account.password)
    assert response.status_code == 200, response.text
    return browser


async def create_organization(
    admin: Browser, name: str | None = None, company_mode: str = "multiple"
) -> dict[str, Any]:
    response = await admin.call(
        "POST",
        "/admin/organizations",
        json={"name": name or f"Org {uuid.uuid4().hex[:8]}", "companyMode": company_mode},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def group_ids(admin: Browser, organization_id: str, *names: str) -> list[str]:
    response = await admin.call("GET", f"/admin/organizations/{organization_id}/groups")
    assert response.status_code == 200, response.text
    by_name = {g["name"]: g["id"] for g in response.json()}
    return [by_name[n] for n in names]


async def create_member(
    admin: Browser, organization_id: str | uuid.UUID, groups: list[str] | None = None
) -> Member:
    """A new account with an initial password; its holder must change it at first sign-in."""
    email = f"m-{uuid.uuid4().hex[:10]}@org.test"
    password = generated_password()
    response = await admin.call(
        "POST",
        f"/admin/organizations/{organization_id}/users",
        json={
            "email": email,
            "name": "Member Person",
            "password": password,
            "groupIds": groups or [],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return Member(
        email=email,
        password=password,
        user_id=uuid.UUID(body["id"]),
        account_id=uuid.UUID(body["accountId"]),
    )


async def ready_member(browser: Browser, member: Member) -> tuple[Browser, Member]:
    """Sign the member in and change the initial password, as the first sign-in requires."""
    await signed_in(browser, member)
    return browser, await change_password(browser, member)


async def change_password(browser: Browser, member: Member) -> Member:
    """Change the password of the member signed in on `browser`; the member with the new one."""
    new_password = generated_password()
    response = await browser.call(
        "PUT",
        "/auth/password",
        json={"currentPassword": member.password, "newPassword": new_password},
    )
    assert response.status_code == 200, response.text
    return Member(member.email, new_password, member.user_id, member.account_id)


async def platform_rows(sql: str, **params: object) -> list[Any]:
    async with db_client.platform_session() as s:
        return list((await s.execute(text(sql), params)).all())


async def platform_execute(sql: str, **params: object) -> None:
    async with db_client.platform_session() as s:
        await s.execute(text(sql), params)
        await s.commit()
