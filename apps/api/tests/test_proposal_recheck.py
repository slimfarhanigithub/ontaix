"""Proposal creation re-checks labels and targets against the database under the decision lock."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from app.auth import Caller
from app.clients import db_client
from app.models.api.drafts import ChangeDraft, ChangePayload
from app.models.storage.base import RoleName, ScopeKind
from app.services import proposal_service
from app.services.ontology_view_service import load_view
from app.utilities.permissions import Grant
from app.utilities.problems import ProblemError
from tests.conftest import TenantFixture
from tests.test_proposals import approved

pytestmark = pytest.mark.asyncio(loop_scope="session")

CONCURRENT_REQUESTS = 4


async def test_concurrent_same_label_creates_answer_one_202_and_409s(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    body = {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "parentId": str(tenant.root_id),
        "label": "Twin",
        "domainKey": "sales",
        "action": "has",
    }

    responses = await asyncio.gather(
        *[
            client.post("/concepts", json=body, headers=tenant.builder.headers)
            for _ in range(CONCURRENT_REQUESTS)
        ]
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [202] + [409] * (CONCURRENT_REQUESTS - 1), codes
    assert all(r.json()["code"] == "duplicate_label" for r in responses if r.status_code == 409)


@pytest.mark.parametrize("change_kind", ["rename", "delete_concept"])
async def test_change_on_a_concept_removed_meanwhile_answers_409(
    client: httpx.AsyncClient, tenant: TenantFixture, change_kind: str
) -> None:
    concept = await approved(client, tenant, f"Gone {change_kind}")
    factory = db_client.get_session_factory()
    async with factory() as stale:
        view = await load_view(stale, tenant.tenant_id)
        delete = await client.delete(f"/concepts/{concept['id']}", headers=tenant.builder.headers)
        assert delete.status_code == 202, delete.text
        assert (
            await client.post(
                f"/proposals/{delete.json()['id']}/approve", headers=tenant.governor.headers
            )
        ).status_code == 200
        payload = ChangePayload(
            concept_id=uuid.UUID(concept["id"]),
            new_label="Renamed" if change_kind == "rename" else None,
        )

        with pytest.raises(ProblemError) as refused:
            await proposal_service.create(
                stale,
                _builder(tenant),
                view,
                ChangeDraft(change_kind=change_kind, payload=payload),
            )
        await stale.rollback()

    assert refused.value.status == 409
    assert refused.value.code == "proposal_decided"


async def test_change_on_a_relation_removed_meanwhile_answers_409(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    a = await approved(client, tenant, "Lender")
    b = await approved(client, tenant, "Loan")
    relation = await client.post(
        "/relations",
        json={"type": "relation", "aId": a["id"], "bId": b["id"], "action": "grants"},
        headers=tenant.builder.headers,
    )
    relation_id = relation.json()["relationId"]
    assert (
        await client.post(
            f"/proposals/{relation.json()['id']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200
    factory = db_client.get_session_factory()
    async with factory() as stale:
        view = await load_view(stale, tenant.tenant_id)
        removal = await client.delete(f"/relations/{relation_id}", headers=tenant.builder.headers)
        assert (
            await client.post(
                f"/proposals/{removal.json()['id']}/approve", headers=tenant.governor.headers
            )
        ).status_code == 200

        with pytest.raises(ProblemError) as refused:
            await proposal_service.create(
                stale,
                _builder(tenant),
                view,
                ChangeDraft(
                    change_kind="edit_relation",
                    payload=ChangePayload(relation_id=uuid.UUID(relation_id), action="issues"),
                ),
            )
        await stale.rollback()

    assert refused.value.status == 409
    assert refused.value.code == "proposal_decided"


def _builder(tenant: TenantFixture) -> Caller:
    return Caller(
        tenant_id=tenant.tenant_id,
        user_id=tenant.builder.user_id,
        name=tenant.builder.subject,
        grants=(Grant(RoleName.BUILDER, ScopeKind.TENANT),),
        everyone_teaches=False,
    )
