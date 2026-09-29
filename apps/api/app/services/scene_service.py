"""The one-call canvas snapshot, limited to the companies the caller may read."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.connector import ConnectorType as ConnectorTypeDto
from app.models.api.scene import Scene
from app.models.api.settings import (
    DEFAULT_LLM_MONTHLY_TOKEN_CAP,
    Appearance,
    AppearanceDefaults,
    Settings,
)
from app.models.api.view_state import ViewState
from app.models.storage.tenant_settings import TenantSettings
from app.repositories import (
    connector_type_repository,
    outbox_repository,
    proposal_repository,
    view_state_repository,
)
from app.services.company_service import readable_companies
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities.artefact_visibility import readable_proposal
from app.utilities.clock import get_clock
from app.utilities.permissions import can_read_proposal, can_read_tenant
from app.utilities.problems import forbidden
from app.utilities.proposal_scope import proposal_company_ids

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = "#3fb8a9"
DEFAULT_SOURCE_COLOUR = "#d6bd8a"


async def get_scene(session: AsyncSession, caller: Caller) -> Scene:
    if not can_read_tenant(caller.grants):
        raise forbidden("No role grants you access to the model")
    open_proposals = await proposal_repository.list_open(session, caller.tenant_id)
    view = await load_view(session, caller.tenant_id, open_proposals)
    companies = readable_companies(caller, view)
    readable_ids = {c.id for c in companies}
    concepts = [c for c in view.live_concepts() if c.company_id in readable_ids]
    concept_ids = {c.id for c in concepts}
    relations = [
        r for r in view.live_relations() if r.a_id in concept_ids and r.b_id in concept_ids
    ]
    proposals = [
        p for p in open_proposals if can_read_proposal(caller.grants, proposal_company_ids(p))
    ]
    settings = view.settings
    view_state = await view_state_repository.get(session, caller.tenant_id)
    connectors = await connector_type_repository.list_in_catalogue_order(session)
    return Scene(
        sequence=await outbox_repository.last_sequence(session, caller.tenant_id),
        server_time=get_clock().now(),
        companies=[view.company_dto(c) for c in companies],
        nodes=[view.concept_dto(c) for c in concepts],
        links=[view.relation_dto(r) for r in relations],
        proposals=[
            readable_proposal(caller.grants, view.proposal_dto(p, view.proposal_artefacts(p)))
            for p in proposals
        ],
        settings=settings_dto(settings),
        appearance=appearance_dto(view, settings),
        view_state=ViewState(
            coverage=view_state.coverage if view_state else False,
        ),
        connectors=[
            ConnectorTypeDto(code=c.code, name=c.name, category=c.category, scope_text=c.scope_text)
            for c in connectors
        ],
    )


def settings_dto(settings: TenantSettings | None) -> Settings:
    if settings is None:
        return Settings(
            voice=True,
            import_docs=True,
            live_teaching=True,
            everyone_teaches=False,
            approval_required=True,
            two_approvers=False,
            auto_attrs=False,
            notify_owners=True,
            multi_company=True,
            cross_company=True,
            animations=True,
            coverage_default=False,
            legend=True,
            read_only_connectors=True,
            refresh="15 min",
            agent_access=True,
            cost_cap=True,
            llm_monthly_token_cap=DEFAULT_LLM_MONTHLY_TOKEN_CAP,
        )
    return Settings(
        voice=settings.voice,
        import_docs=settings.import_docs,
        live_teaching=settings.live_teaching,
        everyone_teaches=settings.everyone_teaches,
        approval_required=True,
        two_approvers=settings.two_approvers,
        auto_attrs=settings.auto_attrs,
        notify_owners=settings.notify_owners,
        multi_company=settings.multi_company,
        cross_company=settings.cross_company,
        animations=settings.animations,
        coverage_default=settings.coverage_default,
        legend=settings.legend,
        read_only_connectors=True,
        refresh=settings.refresh.value,
        agent_access=settings.agent_access,
        cost_cap=settings.cost_cap,
        llm_monthly_token_cap=settings.llm_monthly_token_cap,
        egress_allowlist=list(settings.egress_allowlist or []),
    )


def appearance_dto(view: OntologyView, settings: TenantSettings | None) -> Appearance:
    defaults = {key: t.color for key, t in view.templates.items()}
    return Appearance(
        theme=settings.theme.value if settings else "dark",
        colors={key: view.effective_color(key) for key in view.templates},
        accent=settings.accent if settings else DEFAULT_ACCENT,
        source=settings.source_colour if settings else DEFAULT_SOURCE_COLOUR,
        defaults=AppearanceDefaults(
            colors=defaults, accent=DEFAULT_ACCENT, source=DEFAULT_SOURCE_COLOUR
        ),
    )
