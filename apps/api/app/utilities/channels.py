"""The tenant settings that gate each way content enters: typed text, speech and documents."""

from __future__ import annotations

from app.models.storage.tenant_settings import TenantSettings
from app.utilities.problems import ProblemError, conflict


def ensure_speech_allowed(settings: TenantSettings | None) -> None:
    if settings is not None and not settings.voice:
        raise channel_disabled("voice input is disabled in the admin portal")


def ensure_import_allowed(settings: TenantSettings | None) -> None:
    if settings is not None and not settings.import_docs:
        raise channel_disabled("document import is disabled in the admin portal")


def ensure_live_teaching_allowed(settings: TenantSettings | None) -> None:
    if settings is not None and not settings.live_teaching:
        raise channel_disabled("live teaching is disabled in the admin portal")


def channel_disabled(detail: str) -> ProblemError:
    return conflict("channel_disabled", detail)
