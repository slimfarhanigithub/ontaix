"""Tenant domains: the ring-ordered list, and the proposals that create or edit one."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.drafts import ChangeDraft, ChangePayload
from app.models.api.proposal import Proposal as ProposalDto
from app.models.api.tenant_domain import DomainInput, DomainPatch
from app.models.api.tenant_domain import TenantDomain as TenantDomainDto
from app.services import proposal_service
from app.services.ontology_view_service import load_view
from app.services.rate_limit_service import charge_proposals
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.permissions import can_read_tenant
from app.utilities.problems import forbidden, not_found

logger = logging.getLogger(__name__)


async def list_domains(session: AsyncSession, caller: Caller) -> list[TenantDomainDto]:
    """Every domain of the tenant in ring order, with its effective colour; any role reads it."""
    if not can_read_tenant(caller.grants):
        raise forbidden("No role grants you access to the model")
    view = await load_view(session, caller.tenant_id)
    return [view.domain_dto(d) for d in view.domains.values()]


async def propose_create(session: AsyncSession, caller: Caller, body: DomainInput) -> ProposalDto:
    await charge_proposals(caller)
    view = await load_view(session, caller.tenant_id)
    draft = ChangeDraft(
        change_kind="create_domain",
        payload=ChangePayload(name=body.name, color=body.color, owner=body.owner),
    )
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )


async def propose_edit(
    session: AsyncSession, caller: Caller, domain_key: str, body: DomainPatch
) -> ProposalDto:
    await charge_proposals(caller)
    view = await load_view(session, caller.tenant_id)
    if domain_key not in view.domains:
        raise not_found("domain")
    draft = ChangeDraft(
        change_kind="edit_domain",
        payload=ChangePayload(
            domain_key=domain_key, name=body.name, color=body.color, owner=body.owner
        ),
    )
    proposal = await proposal_service.create(session, caller, view, draft)
    return readable_proposal(
        caller.grants, view.proposal_dto(proposal, view.proposal_artefacts(proposal))
    )
