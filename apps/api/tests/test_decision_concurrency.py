"""Concurrent decisions on one proposal: exactly one wins, the other answers 409."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.auth import Caller
from app.clients import db_client
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import ProposalState, RoleName, ScopeKind
from app.models.storage.concept import Concept
from app.models.storage.proposal import Proposal
from app.models.storage.proposal_approval import ProposalApproval
from app.services import decision_service
from app.utilities.permissions import Grant
from app.utilities.problems import ProblemError
from tests.conftest import Persona, TenantFixture
from tests.test_proposals import propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")

LOCK_WAIT_SECONDS = 0.5


async def test_concurrent_approve_and_reject_exactly_one_wins(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Racer", tenant.root_id)
    ).json()
    proposal_id = uuid.UUID(created["id"])
    concept_id = uuid.UUID(created["conceptId"])
    factory = db_client.get_platform_session_factory()
    first, second = factory(), factory()
    try:
        await decision_service.approve(first, _governor(tenant, tenant.governor), proposal_id)

        async def reject_concurrently() -> None:
            await decision_service.reject(
                second, _governor(tenant, tenant.second_governor), proposal_id, None
            )
            await second.commit()

        task = asyncio.create_task(reject_concurrently())
        await asyncio.sleep(LOCK_WAIT_SECONDS)
        assert not task.done(), "the reject must wait for the approval's transaction"
        await first.commit()
        with pytest.raises(ProblemError) as refused:
            await task
        await second.rollback()
    finally:
        await first.close()
        await second.close()

    assert refused.value.status == 409
    assert refused.value.code == "proposal_decided"
    async with factory() as s:
        proposal = await s.get(Proposal, proposal_id)
        assert proposal is not None and proposal.state is ProposalState.APPROVED
        assert await s.get(Concept, concept_id) is not None
        approvals = (
            await s.scalars(
                select(ProposalApproval).where(ProposalApproval.proposal_id == proposal_id)
            )
        ).all()
        audits = (
            await s.scalars(select(AuditEntry).where(AuditEntry.proposal_id == proposal_id))
        ).all()
    assert len(approvals) == 1
    assert [a.ok for a in audits] == [True]


async def test_concurrent_double_approve_answers_one_200_and_one_409(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Twice", tenant.root_id)
    ).json()

    responses = await asyncio.gather(
        client.post(f"/proposals/{created['id']}/approve", headers=tenant.governor.headers),
        client.post(f"/proposals/{created['id']}/approve", headers=tenant.second_governor.headers),
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    refused = next(r for r in responses if r.status_code == 409)
    assert refused.json()["code"] == "proposal_decided"
    final = (
        await client.get(f"/proposals/{created['id']}", headers=tenant.governor.headers)
    ).json()
    assert final["state"] == "approved"
    assert len(final["approvals"]) == 1


def _governor(tenant: TenantFixture, persona: Persona) -> Caller:
    return Caller(
        tenant_id=tenant.tenant_id,
        user_id=persona.user_id,
        name=persona.subject,
        grants=(Grant(RoleName.GOVERNOR, ScopeKind.TENANT),),
        everyone_teaches=False,
    )
