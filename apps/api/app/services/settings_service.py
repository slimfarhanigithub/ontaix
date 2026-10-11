"""Tenant settings: the read, the immediate audited change, and the companies-may-interact
switch with the removal of every cross-company relation it implies.

Every change is immediate: no proposal, one audit entry per changed key, and a
`settings.changed` event carrying the full settings. The one exception is turning
`crossCompany` off while cross-company relations or proposals exist: that goes through the
dedicated disable endpoint, where the Administrator's typed confirmation creates and approves a
bulk `remove_cross_company_links` change proposal in the same transaction.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Any

from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.proposal import Artefacts
from app.models.api.settings import (
    MAX_IMPACT_SAMPLES,
    CrossCompanyDisable,
    CrossCompanyDisabled,
    CrossCompanyImpact,
    CrossCompanyPair,
    Settings,
    SettingsPatch,
)
from app.models.decisions.decision_outcome import DecisionOutcome
from app.models.storage.base import (
    ChangeKind,
    CompanyMode,
    ProposalState,
    ProposalType,
    RefreshInterval,
)
from app.models.storage.proposal import Proposal
from app.models.storage.relation import Relation
from app.models.storage.tenant_settings import TenantSettings
from app.repositories import (
    organization_settings_repository,
    proposal_approval_repository,
    proposal_repository,
    relation_repository,
    tenant_settings_repository,
)
from app.services import audit_service, decision_lock_service, outbox_service
from app.services.decision_event_service import emit_proposal_event
from app.services.ontology_view_service import OntologyView, load_view
from app.services.proposal_store_service import store
from app.services.rejection_service import OPEN_STATES, reject_one
from app.services.scene_service import settings_dto
from app.utilities.clock import get_clock
from app.utilities.layout import CONFLICT_COLOR
from app.utilities.permissions import can_manage, can_read_tenant
from app.utilities.problems import conflict, forbidden
from app.utilities.proposal_relations import touched_relation_ids
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

SETTINGS_CHANGED_EVENT = "settings.changed"
CROSS_COMPANY_DISABLED_EVENT = "settings.cross_company_disabled"
AUDIT_KIND = "setting"
CONFIRMATION_WORD = "disable"
LOCKED_SETTINGS = frozenset({"approval_required", "read_only_connectors"})
MANAGE_DETAIL = "Changing settings requires Administrator"
READ_DETAIL = "No role grants you access to the settings"
LOCKED_ON_DETAIL = "{key} is always on"
SINGLE_COMPANY_DETAIL = "Several companies stay off while the organization has one company only"
CONFIRMATION_REQUIRED_DETAIL = "companies already interact; confirm by typing disable"
CONFIRMATION_MISMATCH_DETAIL = "type disable to confirm"
ALREADY_DISABLED_DETAIL = "companies already do not interact"
DISABLE_WHY = "confirmed by typing disable"
DISABLE_CAPTION = "Companies no longer interact; their shared relationships left the model."


async def get_settings(session: AsyncSession, caller: Caller) -> Settings:
    if not can_read_tenant(caller.grants):
        raise forbidden(READ_DETAIL)
    settings = await tenant_settings_repository.get(session, caller.tenant_id)
    mode = await organization_settings_repository.company_mode(session, caller.tenant_id)
    return settings_dto(settings, mode)


async def update_settings(session: AsyncSession, caller: Caller, patch: SettingsPatch) -> Settings:
    """Write every key of the patch whose value differs, one audit entry each, then one
    `settings.changed` event naming them. A locked setting answers `409 locked_setting`, and so
    does `multiCompany` on while the organization is in single company mode."""
    if not can_manage(caller.grants):
        raise forbidden(MANAGE_DETAIL)
    for key in LOCKED_SETTINGS & patch.model_fields_set:
        raise conflict("locked_setting", LOCKED_ON_DETAIL.format(key=to_camel(key)))
    mode = await organization_settings_repository.company_mode(session, caller.tenant_id)
    if patch.multi_company and mode is CompanyMode.SINGLE:
        raise conflict("locked_setting", SINGLE_COMPANY_DETAIL)
    settings = await _settings_row(session, caller.tenant_id)
    if patch.cross_company is False and settings.cross_company:
        # Under the decision lock, so no cross-company proposal lands between this check and
        # the commit.
        await decision_lock_service.acquire(session, caller.tenant_id)
        view = await load_view(session, caller.tenant_id)
        open_proposals = await proposal_repository.lock_open(session, caller.tenant_id)
        if _cross_company_relations(view) or _cross_company_proposals(view, open_proposals):
            raise conflict("confirmation_required", CONFIRMATION_REQUIRED_DETAIL)
    values: dict[str, Any] = {}
    for key in patch.model_fields_set:
        value = _stored_value(key, getattr(patch, key))
        if value != getattr(settings, key):
            values[key] = value
    if not values:
        return settings_dto(settings, mode)
    await tenant_settings_repository.update(session, settings, **values)
    for key, value in values.items():
        await audit_service.record(
            session,
            caller.tenant_id,
            caller.actor,
            AUDIT_KIND,
            _audit_text(key, value),
            True,
            company_ids=[],
        )
    dto = settings_dto(settings, mode)
    await _emit_settings_changed(session, caller, dto, [to_camel(key) for key in values])
    return dto


async def cross_company_impact(session: AsyncSession, caller: Caller) -> CrossCompanyImpact:
    """What disabling companies-may-interact would remove: the approved cross-company
    relations by company pair, the open proposals touching one, and up to six samples."""
    if not can_manage(caller.grants):
        raise forbidden(MANAGE_DETAIL)
    open_proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, open_proposals)
    relations = _cross_company_relations(view)
    pairs = Counter(_pair_names(view, r) for r in relations)
    return CrossCompanyImpact(
        relations=len(relations),
        pending_proposals=len(_cross_company_proposals(view, open_proposals)),
        pairs=[
            CrossCompanyPair(company_a=a, company_b=b, count=count)
            for (a, b), count in sorted(pairs.items())
        ],
        samples=[_sample(view, r) for r in relations[:MAX_IMPACT_SAMPLES]],
    )


async def disable_cross_company(
    session: AsyncSession, caller: Caller, body: CrossCompanyDisable
) -> CrossCompanyDisabled:
    """Turn companies-may-interact off in one transaction, under the tenant decision lock:
    a bulk `remove_cross_company_links` proposal is stored and approved by the confirmation,
    every open proposal touching a cross-company relation is rejected, every approved
    cross-company relation leaves, the setting goes off and the outcome is audited."""
    if not can_manage(caller.grants):
        raise forbidden(MANAGE_DETAIL)
    if body.confirmation != CONFIRMATION_WORD:
        raise conflict("confirmation_mismatch", CONFIRMATION_MISMATCH_DETAIL)
    await decision_lock_service.acquire(session, caller.tenant_id)
    open_proposals = await proposal_repository.lock_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, open_proposals)
    settings = await _settings_row(session, caller.tenant_id)
    if not settings.cross_company:
        raise conflict("cross_company_disabled", ALREADY_DISABLED_DETAIL)
    relations = _cross_company_relations(view)
    rejected = _cross_company_proposals(view, open_proposals)
    proposal = await _store_removal(session, caller, view, relations)
    approval = await proposal_approval_repository.create(
        session, caller.tenant_id, proposal.id, 1, caller.user_id
    )
    view.register_approval(approval)
    await proposal_repository.mark_decided(
        session, proposal, ProposalState.APPROVED, get_clock().now()
    )
    outcome = DecisionOutcome(artefacts=Artefacts())
    for q in rejected:
        # A dependant of an earlier rejection in this loop has already left with it.
        if q.state not in OPEN_STATES:
            continue
        cascaded = await reject_one(session, caller, view, q, open_proposals, None, True)
        outcome.add_cascaded(view.proposal_dto(q, cascaded.artefacts), proposal_company_ids(q))
        outcome.absorb_cascade(cascaded)
    removed_ids = await _remove_relations(session, caller, view, proposal, relations, outcome)
    if settings.cross_company:
        await tenant_settings_repository.update(session, settings, cross_company=False)
    mode = await organization_settings_repository.company_mode(session, caller.tenant_id)
    dto = settings_dto(settings, mode)
    count = len(removed_ids)
    outcome.caption = DISABLE_CAPTION
    outcome.audit = await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        f"companies may interact disabled · {_relationships(count)} removed",
        True,
        proposal.id,
        company_ids=[],
    )
    await emit_proposal_event(session, caller, view, proposal, "proposal.approved", outcome, True)
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        CROSS_COMPANY_DISABLED_EVENT,
        {
            "removedRelationIds": [str(i) for i in removed_ids],
            "rejectedProposalIds": [str(q.id) for q in rejected],
            "proposalId": str(proposal.id),
        },
        bulk=True,
    )
    await _emit_settings_changed(session, caller, dto, ["crossCompany"])
    return CrossCompanyDisabled(
        removed_relations=count,
        rejected_proposals=len(rejected),
        proposal=view.proposal_dto(proposal, outcome.artefacts),
        audit=outcome.audit,
        settings=dto,
    )


async def _settings_row(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettings:
    settings = await tenant_settings_repository.get(session, tenant_id)
    if settings is None:
        settings = await tenant_settings_repository.create(session, tenant_id)
    return settings


def _stored_value(key: str, value: Any) -> Any:
    """The column value of one patch key: the refresh interval as its enum, lists as lists."""
    if key == "refresh":
        return RefreshInterval(value)
    if key == "egress_allowlist":
        return list(value)
    return value


def _audit_text(key: str, value: Any) -> str:
    name = to_camel(key)
    if isinstance(value, bool):
        return f"{name} {'enabled' if value else 'disabled'}"
    if isinstance(value, RefreshInterval):
        return f"refresh interval {value.value}"
    if isinstance(value, list):
        return f"{name} set to {len(value)} host{'' if len(value) == 1 else 's'}"
    return f"{name} set to {value}"


async def _emit_settings_changed(
    session: AsyncSession, caller: Caller, settings: Settings, changed: list[str]
) -> None:
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        SETTINGS_CHANGED_EVENT,
        {"settings": settings.model_dump(mode="json", by_alias=True), "changed": changed},
    )


def _is_cross_company(view: OntologyView, relation: Relation) -> bool:
    a, b = view.concepts.get(relation.a_id), view.concepts.get(relation.b_id)
    return a is not None and b is not None and a.company_id != b.company_id


def _cross_company_relations(view: OntologyView) -> list[Relation]:
    """The approved relations and equivalences joining two companies; a pending one belongs to
    the open proposal that created it and leaves with that proposal's rejection."""
    return [r for r in view.live_relations() if not r.pending and _is_cross_company(view, r)]


def _cross_company_proposals(view: OntologyView, open_proposals: list[Proposal]) -> list[Proposal]:
    """The open proposals that created, target or depend on a relation joining two companies."""
    found: list[Proposal] = []
    for proposal in open_proposals:
        if proposal.state not in OPEN_STATES:
            continue
        for rid in touched_relation_ids(proposal):
            relation = view.relations.get(rid)
            if relation is not None and _is_cross_company(view, relation):
                found.append(proposal)
                break
    return found


def _pair_names(view: OntologyView, relation: Relation) -> tuple[str, str]:
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    names = sorted((view.companies[a.company_id].name, view.companies[b.company_id].name))
    return names[0], names[1]


def _sample(view: OntologyView, relation: Relation) -> str:
    a, b = view.concepts[relation.a_id], view.concepts[relation.b_id]
    return f"{a.label} {relation.label} {b.label}"


def _relationships(count: int) -> str:
    return f"{count} cross-company relationship{'' if count == 1 else 's'}"


async def _store_removal(
    session: AsyncSession, caller: Caller, view: OntologyView, relations: list[Relation]
) -> Proposal:
    """The bulk change proposal the confirmation approves: tenant-wide, since it touches every
    company a cross-company relation joins."""
    count = len(relations)
    company_ids: list[uuid.UUID] = []
    for relation in relations:
        for end in (view.concepts[relation.a_id], view.concepts[relation.b_id]):
            company_ids.append(end.company_id)
    return await store(
        session,
        caller.actor,
        view,
        type=ProposalType.CHANGE,
        change_kind=ChangeKind.REMOVE_CROSS_COMPANY_LINKS,
        title=f"Remove {_relationships(count)}",
        color=CONFLICT_COLOR,
        company_id=None,
        domain_product_id=None,
        parent_label=None,
        deps=[],
        wait_for=None,
        html=f"Remove {_relationships(count)}",
        why=DISABLE_WHY,
        caption=DISABLE_CAPTION,
        payload={"relationIds": [str(r.id) for r in relations]},
        touched_company_ids=company_ids,
        concept_id=None,
        relation_id=None,
        bulk=True,
    )


async def _remove_relations(
    session: AsyncSession,
    caller: Caller,
    view: OntologyView,
    proposal: Proposal,
    relations: list[Relation],
    outcome: DecisionOutcome,
) -> list[uuid.UUID]:
    """Every approved cross-company relation leaves with its own `relation.removed` event, so
    each company's canvas drops the line."""
    now = get_clock().now()
    removed: list[uuid.UUID] = []
    for relation in relations:
        dto = view.relation_dto(relation)
        await relation_repository.mark_dying(session, relation, now)
        outcome.artefacts.relations.append(view.relation_dto(relation))
        await relation_repository.delete(session, relation)
        view.forget_relation(relation.id)
        removed.append(relation.id)
        await outbox_service.emit(
            session,
            caller.tenant_id,
            caller.actor,
            "relation.removed",
            {"relationId": str(relation.id), "dying": True, "proposalId": str(proposal.id)},
            company_ids=dto.company_ids,
            bulk=True,
        )
    return removed
