"""Relation actions are normalised on every path, and duplicates compare normalised forms."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from app.clients import db_client
from app.utilities.action_text import has_refused_character, normalise_action
from tests.conftest import TenantFixture
from tests.test_proposals import approved


def test_normalise_action() -> None:
    assert normalise_action("  Sells   TO ") == "sells to"
    assert normalise_action("ＩＳ　Ａ") == "is a"
    assert not has_refused_character("focuses on")
    for bad in ("is­a", "a<b", "x​y", "x\U000e0041y", "x y", "x؀y"):
        assert has_refused_character(bad), repr(bad)


@pytest.mark.asyncio(loop_scope="session")
async def test_birth_actions_and_new_relations_are_normalised_and_duplicates_compared(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    plant = await approved(client, tenant, "Plant")
    line = (
        await client.post(
            "/concepts",
            json={
                "type": "concept",
                "companyId": str(tenant.company_id),
                "parentId": plant["id"],
                "label": "Line",
                "domainKey": "production",
                "action": "  Feeds  INTO ",
            },
            headers=tenant.builder.headers,
        )
    ).json()
    async with db_client.get_platform_session_factory()() as s:
        label = (
            await s.execute(
                text("SELECT label FROM ontaix.relation WHERE b_id = :b"),
                {"b": line["conceptId"]},
            )
        ).scalar_one()
    assert label == "feeds into"

    duplicate = await client.post(
        "/relations",
        json={"aId": plant["id"], "bId": line["conceptId"], "action": "FEEDS   into"},
        headers=tenant.builder.headers,
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["code"] == "duplicate_relation"
