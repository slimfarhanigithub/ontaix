"""Appearance: the theme, the tenant-wide domain colours, the accent and the source colour.

The domain colours are overrides in `tenant_settings.colors`, keyed by domain key; a domain
without one shows its default colour. An approved domain edit writes the same override, so a
domain keeps one colour in every company.
"""

from __future__ import annotations

import logging

from app.models.api.settings import Appearance, AppearanceDefaults
from app.models.storage.tenant_settings import TenantSettings
from app.services.ontology_view_service import OntologyView

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = "#3fb8a9"
DEFAULT_SOURCE_COLOUR = "#d6bd8a"


def appearance_dto(view: OntologyView, settings: TenantSettings | None) -> Appearance:
    defaults = {key: t.default_color for key, t in view.domains.items()}
    return Appearance(
        theme=settings.theme.value if settings else "dark",
        colors={key: view.effective_color(key) for key in view.domains},
        accent=settings.accent if settings else DEFAULT_ACCENT,
        source=settings.source_colour if settings else DEFAULT_SOURCE_COLOUR,
        defaults=AppearanceDefaults(
            colors=defaults, accent=DEFAULT_ACCENT, source=DEFAULT_SOURCE_COLOUR
        ),
    )
