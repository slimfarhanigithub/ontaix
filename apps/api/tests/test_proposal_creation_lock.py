"""Proposal creation takes the tenant decision lock, and the lock wait is bounded."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from app.auth import Caller
from app.clients import db_client
from app.models.api.drafts import ConceptDraft
from app.models.storage.base import ProposalState, RoleName, ScopeKind
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.repositories import proposal_repository
from app.services import decision_service, proposal_service
from app.services.ontology_view_service import load_view
from app.utilities.permissions import Grant
from app.utilities.problems import ProblemError
from tests.conftest import Persona, TenantFixture
from tests.test_proposals import propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")

LOCK_WAIT_SECONDS = 0.5
SHORT_LOCK_TIMEOUT_MS = 200


async def test_child_created_while_its_parent_is_rejected_is_cascaded(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    parent = (
        await propose_concept(
            client, tenant, tenant.builder, "RaceParent", tenant.root_id, domain_key="sales"
        )
    ).json()
    factory = db_client.get_session_factory()
    creating, rejecting = factory(), factory()
    try:
        view = await load_view(creating, tenant.tenant_id)
        child = await proposal_service.create(
            creating, _caller(tenant, tenant.builder, RoleName.BUILDER), view, _child(tenant)
        )
        child_id, child_concept_id = child.id, child.concept_id

        async def reject_concurrently() -> None:
            await decision_service.reject(
                rejecting,
                _caller(tenant, tenant.governor, RoleName.GOVERNOR),
                uuid.UUID(parent["id"]),
                None,
            )
            await rejecting.commit()

        task = asyncio.create_task(reject_concurrently())
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not task.done(), "the rejection must wait for the creation's transaction"
        await creating.commit()
        await task
    finally:
        await creating.close()
        await rejecting.close()

    async with factory() as s:
        proposal = await s.get(Proposal, child_id)
        assert proposal is not None and proposal.state is ProposalState.REJECTED
        assert await s.get(Concept, child_concept_id) is None


async def test_child_proposed_after_its_parent_was_rejected_answers_409(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    parent = (
        await propose_concept(
            client, tenant, tenant.builder, "LateParent", tenant.root_id, domain_key="sales"
        )
    ).json()
    factory = db_client.get_session_factory()
    creating, rejecting = factory(), factory()
    try:
        view = await load_view(creating, tenant.tenant_id)
        await decision_service.reject(
            rejecting,
            _caller(tenant, tenant.governor, RoleName.GOVERNOR),
            uuid.UUID(parent["id"]),
            None,
        )
        task = asyncio.create_task(
            proposal_service.create(
                creating,
                _caller(tenant, tenant.builder, RoleName.BUILDER),
                view,
                _child(tenant, parent="LateParent", label="LateChild"),
            )
        )
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not task.done(), "the creation must wait for the rejection's transaction"
        await rejecting.commit()
        with pytest.raises(ProblemError) as refused:
            await task
        await creating.rollback()
    finally:
        await creating.close()
        await rejecting.close()

    assert refused.value.status == 409
    assert refused.value.code == "proposal_decided"


async def test_decision_lock_wait_is_bounded_and_answers_503(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = (await propose_concept(client, tenant, tenant.builder, "Held", tenant.root_id)).json()
    waiting = (
        await propose_concept(client, tenant, tenant.builder, "Waiting", tenant.root_id)
    ).json()
    monkeypatch.setattr(proposal_repository, "DECISION_LOCK_TIMEOUT_MS", SHORT_LOCK_TIMEOUT_MS)
    holder = db_client.get_session_factory()()
    try:
        await decision_service.approve(
            holder, _caller(tenant, tenant.governor, RoleName.GOVERNOR), uuid.UUID(held["id"])
        )

        response = await client.post(
            f"/proposals/{waiting['id']}/approve", headers=tenant.second_governor.headers
        )
    finally:
        await holder.rollback()
        await holder.close()

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "unavailable"
    retried = await client.post(
        f"/proposals/{waiting['id']}/approve", headers=tenant.second_governor.headers
    )
    assert retried.status_code == 200, retried.text


def _child(
    tenant: TenantFixture, parent: str = "RaceParent", label: str = "RaceChild"
) -> ConceptDraft:
    return ConceptDraft(
        company_id=tenant.company_id,
        parent_label=parent,
        label=label,
        domain_key="sales",
        action="has",
    )


def _caller(tenant: TenantFixture, persona: Persona, role: RoleName) -> Caller:
    return Caller(
        tenant_id=tenant.tenant_id,
        user_id=persona.user_id,
        name=persona.subject,
        grants=(Grant(role, ScopeKind.TENANT),),
        everyone_teaches=False,
    )
