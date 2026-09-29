"""`POST /speech/token`: a short-lived Azure AI Speech token for the teach bar microphone.

The caller must be allowed to teach the company (`proposal.create` in its scope) with the
`voice` setting on. Each call spends one unit of the caller's hourly `speech` budget, and each
issued token writes one audit entry that never holds the token. When no Speech resource is
configured, or the token cannot be minted, the answer is `503 unavailable` and the Studio uses
the browser's own recogniser.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.clients.speech_token_client import SpeechTokenUnavailable, get_speech_token_client
from app.config import get_settings
from app.models.api.speech import SpeechToken, SpeechTokenRequest
from app.models.storage.base import ScopeKind
from app.services import audit_service
from app.services.ontology_view_service import load_view
from app.services.rate_limit_service import Budget, charge
from app.utilities.channels import ensure_speech_allowed
from app.utilities.permissions import Scope, can_propose, can_read
from app.utilities.problems import ProblemError, forbidden, not_found

logger = logging.getLogger(__name__)

AUDIT_KIND = "speech"
AUDIT_WHAT = "Speech recognition token issued"


async def mint(session: AsyncSession, caller: Caller, body: SpeechTokenRequest) -> SpeechToken:
    view = await load_view(session, caller.tenant_id)
    company = view.companies.get(body.company_id)
    if company is None or not can_read(caller.grants, company.id):
        raise not_found("company")
    if not _can_teach(caller, company.id):
        raise forbidden("Your roles do not allow teaching this company")
    ensure_speech_allowed(view.settings)
    settings = get_settings()
    client = get_speech_token_client()
    if client is None or settings.speech_resource_id is None:
        raise _unavailable("speech recognition is not configured")
    await charge(Budget.SPEECH, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    try:
        access = await client.access_token()
    except SpeechTokenUnavailable:
        raise _unavailable("a speech recognition token could not be obtained") from None
    await audit_service.record(
        session,
        caller.tenant_id,
        caller.actor,
        AUDIT_KIND,
        AUDIT_WHAT,
        True,
        company_ids=[company.id],
    )
    return SpeechToken(
        token=f"aad#{settings.speech_resource_id}#{access.token}",
        region=settings.speech_region,
        expires_at=datetime.fromtimestamp(access.expires_on, UTC),
        language=settings.speech_language,
    )


def _can_teach(caller: Caller, company_id: uuid.UUID) -> bool:
    """`proposal.create` in the company's scope; a domain-scoped proposing role reaches its
    domain product in every company, so it teaches every company too."""
    if can_propose(caller.grants, Scope(company_id=company_id), caller.everyone_teaches):
        return True
    return any(
        g.scope_kind is ScopeKind.DOMAIN
        and can_propose((g,), Scope(domain_key=g.domain_key), caller.everyone_teaches)
        for g in caller.grants
    )


def _unavailable(detail: str) -> ProblemError:
    return ProblemError(503, "unavailable", detail)
