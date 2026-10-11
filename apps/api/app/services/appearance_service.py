"""Appearance: the tenant-wide domain colours, the accent and the source colour.

The domain colours are overrides in `tenant_settings.colors`, keyed by domain key; a domain
without one shows its default colour. An approved domain edit writes the same override, so a
domain keeps one colour in every company. An Administrator changes the values immediately:
each change is audited and announced by one `appearance.changed` event.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.settings import Appearance, AppearanceDefaults, AppearancePatch
from app.models.storage.tenant_settings import TenantSettings
from app.repositories import tenant_settings_repository
from app.services import audit_service, outbox_service
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities.permissions import can_manage, can_read_tenant
from app.utilities.problems import forbidden, validation_failed

logger = logging.getLogger(__name__)

# The design system's crimson accent and brass source colour, the light values of its tokens.
DEFAULT_ACCENT = "#d30c55"
DEFAULT_SOURCE_COLOUR = "#d6bd8a"
APPEARANCE_CHANGED_EVENT = "appearance.changed"
AUDIT_KIND = "appearance"
MANAGE_DETAIL = "Changing the appearance requires Administrator"
READ_DETAIL = "No role grants you access to the appearance"
RESET_TEXT = "colours reset"


def appearance_dto(view: OntologyView, settings: TenantSettings | None) -> Appearance:
    defaults = {key: t.default_color for key, t in view.domains.items()}
    return Appearance(
        colors={key: view.effective_color(key) for key in view.domains},
        accent=settings.accent if settings else DEFAULT_ACCENT,
        source=settings.source_colour if settings else DEFAULT_SOURCE_COLOUR,
        defaults=AppearanceDefaults(
            colors=defaults, accent=DEFAULT_ACCENT, source=DEFAULT_SOURCE_COLOUR
        ),
    )


async def get_appearance(session: AsyncSession, caller: Caller) -> Appearance:
    if not can_read_tenant(caller.grants):
        raise forbidden(READ_DETAIL)
    view = await load_view(session, caller.tenant_id)
    return appearance_dto(view, view.settings)


async def update_appearance(
    session: AsyncSession, caller: Caller, patch: AppearancePatch
) -> Appearance:
    """Write the colour overrides, accent and source colour the patch names; a colour of an
    unknown domain key is a validation error. Only values that differ are written, audited
    and named in `changed`."""
    if not can_manage(caller.grants):
        raise forbidden(MANAGE_DETAIL)
    view = await load_view(session, caller.tenant_id)
    for key in patch.colors or {}:
        if key not in view.domains:
            raise validation_failed(f"colors.{key}", f"unknown domain key {key!r}")
    settings = await _settings_row(session, view)
    changed: list[str] = []
    texts: list[str] = []
    colors = {
        key: color
        for key, color in (patch.colors or {}).items()
        if color != view.effective_color(key)
    }
    if colors:
        await tenant_settings_repository.update(
            session, settings, colors={**(settings.colors or {}), **colors}
        )
        changed.append("colors")
        texts.extend(f"{view.domains[key].name} colour set to {c}" for key, c in colors.items())
    if patch.accent is not None and patch.accent != settings.accent:
        await tenant_settings_repository.update(session, settings, accent=patch.accent)
        changed.append("accent")
        texts.append(f"accent set to {patch.accent}")
    if patch.source is not None and patch.source != settings.source_colour:
        await tenant_settings_repository.update(session, settings, source_colour=patch.source)
        changed.append("source")
        texts.append(f"source colour set to {patch.source}")
    dto = appearance_dto(view, settings)
    if not changed:
        return dto
    for text in texts:
        await _audit(session, caller, text)
    await _emit_changed(session, caller, dto, changed)
    return dto


async def reset_appearance(session: AsyncSession, caller: Caller) -> Appearance:
    """Every domain back to its default colour, the accent and the source colour back to the
    design system's values."""
    if not can_manage(caller.grants):
        raise forbidden(MANAGE_DETAIL)
    view = await load_view(session, caller.tenant_id)
    settings = await _settings_row(session, view)
    await tenant_settings_repository.update(
        session, settings, colors={}, accent=DEFAULT_ACCENT, source_colour=DEFAULT_SOURCE_COLOUR
    )
    dto = appearance_dto(view, settings)
    await _audit(session, caller, RESET_TEXT)
    await _emit_changed(session, caller, dto, ["colors", "accent", "source"])
    return dto


async def _settings_row(session: AsyncSession, view: OntologyView) -> TenantSettings:
    if view.settings is None:
        view.settings = await tenant_settings_repository.create(session, view.tenant_id)
    return view.settings


async def _audit(session: AsyncSession, caller: Caller, what: str) -> None:
    await audit_service.record(
        session, caller.tenant_id, caller.actor, AUDIT_KIND, what, True, company_ids=[]
    )


async def _emit_changed(
    session: AsyncSession, caller: Caller, appearance: Appearance, changed: list[str]
) -> None:
    await outbox_service.emit(
        session,
        caller.tenant_id,
        caller.actor,
        APPEARANCE_CHANGED_EVENT,
        {"appearance": appearance.model_dump(mode="json", by_alias=True), "changed": changed},
        company_ids=[],
    )
