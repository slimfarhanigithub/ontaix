"""OCR of the image-only pages of an imported PDF, bounded by page caps, budgets and the clock.

In order: at most `ocr_max_pages` image-only pages per import (`413` above); OCR must be
configured and on - the tenant's `llmMonthlyTokenCap` and `ocrMonthlyPageCap` both above 0 -
else `503`; one unit of the caller's hourly `ocr` budget per page (`429`); the pages reserved
against the tenant's monthly page cap in a short transaction of their own (`503` when it would
pass). Then one call with the page list within `ocr_timeout_seconds`. The reservation settles to
the pages the provider processed and one `llm_call` row with purpose `document_ocr` is stored,
whatever the outcome. A timeout, a failure or a result missing any asked page refuses the whole
import with `503`, so a document is never stored with pages silently missing.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.auth import Caller
from app.clients.ocr_client import OcrCallError, OcrClient, OcrRequest, OcrTimeout, get_ocr_client
from app.config import get_settings
from app.models.api.settings import DEFAULT_LLM_MONTHLY_TOKEN_CAP, DEFAULT_OCR_MONTHLY_PAGE_CAP
from app.models.storage.tenant_settings import TenantSettings
from app.repositories.llm_call_repository import CallRecord
from app.services import llm_usage_service
from app.services.rate_limit_service import Budget, charge
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

UNAVAILABLE_DETAIL = "scanned pages cannot be read right now; the document was not imported"


async def recognise(
    caller: Caller, settings: TenantSettings | None, pdf: bytes, pages: list[int]
) -> dict[int, str]:
    """The recognised Markdown of each image-only page, or a refusal of the whole import."""
    config = get_settings()
    if len(pages) > config.ocr_max_pages:
        raise ProblemError(
            413,
            "payload_too_large",
            f"more than {config.ocr_max_pages} scanned pages; split the document",
        )
    client = get_ocr_client()
    token_cap = settings.llm_monthly_token_cap if settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
    page_cap = settings.ocr_monthly_page_cap if settings else DEFAULT_OCR_MONTHLY_PAGE_CAP
    if client is None or token_cap == 0 or page_cap == 0:
        raise _unavailable("OCR is not configured or turned off")
    await charge(Budget.OCR, caller.tenant_id, caller.actor_kind.value, caller.user_id, len(pages))
    reservation = await llm_usage_service.reserve_pages(caller.tenant_id, len(pages), page_cap)
    if reservation is None:
        raise _unavailable("the monthly OCR page cap is reached")
    request = OcrRequest(pdf=pdf, pages=pages, timeout_seconds=config.ocr_timeout_seconds)
    try:
        result = await client.recognise(request)
    except OcrCallError as exc:
        outcome = "timeout" if isinstance(exc, OcrTimeout) else "provider_error"
        await llm_usage_service.settle_pages(
            reservation, _record(caller, client, exc.pages_processed, 0, 0, exc.latency_ms, outcome)
        )
        raise _unavailable(f"the OCR call ended with {outcome}") from exc
    missing = [p for p in pages if p not in result.pages]
    outcome = "invalid_output" if missing else "used"
    await llm_usage_service.settle_pages(
        reservation,
        _record(
            caller,
            client,
            result.pages_processed,
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
            outcome,
        ),
    )
    if missing:
        raise _unavailable(f"the OCR result lacks {len(missing)} of the asked pages")
    return {p: result.pages[p] for p in pages}


def _record(
    caller: Caller,
    client: OcrClient,
    pages: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    outcome: str,
) -> CallRecord:
    cost = float(round(client.price.eur_per_page * Decimal(pages), 6))
    return CallRecord(
        tenant_id=caller.tenant_id,
        actor_kind=caller.actor_kind.value,
        actor_id=caller.user_id,
        company_id=None,
        purpose=llm_usage_service.DOCUMENT_OCR,
        provider=client.provider,
        model=client.model,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        cost_eur=cost,
        latency_ms=min(300_000, max(0, latency_ms)),
        outcome=outcome,
        pages=min(2000, max(0, pages)),
    )


def _unavailable(reason: str) -> ProblemError:
    logger.warning("OCR refused an import: %s", reason)
    return ProblemError(503, "unavailable", UNAVAILABLE_DETAIL)
