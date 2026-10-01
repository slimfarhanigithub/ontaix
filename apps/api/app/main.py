"""FastAPI application entry point for the Ontaix API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import DEV_USER_HEADER
from app.clients.db_client import dispose_engine
from app.clients.llm_client import check_llm_configuration, warm_llm_clients
from app.clients.ocr_client import check_ocr_configuration
from app.config import get_settings

# Every ontology table has a foreign key to `tenant`; its mapping must be registered before the
# first flush, and no request path imports it otherwise.
from app.models.storage import tenant as _tenant_mapping  # noqa: F401
from app.routers import (
    admin_audit,
    admin_organization_users,
    admin_organizations,
    admin_support_session,
    audit,
    auth,
    companies,
    concepts,
    cost,
    domain_products,
    domains,
    expansions,
    extractions,
    health,
    imports,
    ontology_imports,
    proposals,
    relations,
    scene,
    speech,
    teach,
)
from app.services import (
    auth_upkeep_service,
    document_extraction_runner_service,
    password_hash_service,
    retention_purge_service,
)
from app.services.import_purge_service import purge_periodically
from app.utilities.contention import is_contention
from app.utilities.db_errors import constraint_name
from app.utilities.problems import ProblemError, busy, conflict

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
PROBLEM_MEDIA_TYPE = "application/problem+json"
CONTENTION_DETAIL = "the request met concurrent work on the same data; try again"
# Constraints the company-mode triggers raise, answered as the conflicts they stand for.
TRIGGER_CONFLICTS = {
    "company_limit": "This organization has one company only",
    "locked_setting": "Several companies stay off while the organization has one company only",
}
HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    413: "payload_too_large",
    415: "unsupported_media_type",
}


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Runs the expired-import purge, the retention purge, the sign-in upkeep and the
    whole-document extraction runner for the life of the process, warms the language model
    clients and the dummy password hash in the background, and cancels them all on shutdown."""
    settings = get_settings()
    tasks = [
        asyncio.create_task(warm_llm_clients(), name="llm-warm-up"),
        asyncio.create_task(password_hash_service.warm(), name="password-hash-warm-up"),
        asyncio.create_task(auth_upkeep_service.run_periodically(), name="sign-in-upkeep"),
        asyncio.create_task(
            purge_periodically(settings.import_purge_interval_seconds), name="import-purge"
        ),
        asyncio.create_task(
            retention_purge_service.purge_periodically(settings.retention_purge_interval_seconds),
            name="retention-purge",
        ),
        asyncio.create_task(
            document_extraction_runner_service.run_periodically(
                settings.document_extraction_poll_seconds
            ),
            name="document-extraction-runner",
        ),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI application and mount every router under /api/v1."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    check_llm_configuration(settings)
    check_ocr_configuration(settings)
    if settings.accepts_dev_identity_header:
        logger.warning(
            "ONTAIX_DEV_IDENTITY_HEADER is on in %s: the %s header is accepted without any"
            " other credential",
            settings.environment,
            DEV_USER_HEADER,
        )

    application = FastAPI(title=settings.app_name, version="1.0.0", lifespan=_lifespan)
    application.include_router(health.router)
    for module in (
        auth,
        admin_organizations,
        admin_organization_users,
        admin_support_session,
        admin_audit,
        scene,
        companies,
        domains,
        domain_products,
        concepts,
        relations,
        proposals,
        expansions,
        teach,
        speech,
        imports,
        ontology_imports,
        extractions,
        audit,
        cost,
    ):
        application.include_router(module.router, prefix=API_PREFIX)
    application.include_router(health.router, prefix=API_PREFIX)

    application.add_exception_handler(ProblemError, _problem_handler)
    application.add_exception_handler(RequestValidationError, _validation_handler)
    application.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    application.add_exception_handler(DBAPIError, _database_error_handler)
    return application


def _problem_response(problem: ProblemError, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.body(request.url.path),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=problem.headers,
    )


async def _problem_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return _problem_response(exc, request)


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"),
            "message": e.get("msg", ""),
        }
        for e in exc.errors()
    ]
    return _problem_response(
        ProblemError(422, "validation_failed", "the body is invalid", errors=errors), request
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = HTTP_STATUS_CODES.get(
        exc.status_code, "bad_request" if exc.status_code < 500 else "unavailable"
    )
    detail = exc.detail if isinstance(exc.detail, str) else None
    return _problem_response(ProblemError(exc.status_code, code, detail), request)


async def _database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lock timeouts, deadlocks and serialisation failures answer `503 busy`; the transaction
    was rolled back, so the client retries the same request. A refusal of the company-mode
    triggers answers its `409`. Any other database error stays a server error."""
    name = constraint_name(exc)
    if name in TRIGGER_CONFLICTS:
        return _problem_response(conflict(name, TRIGGER_CONFLICTS[name]), request)
    if not is_contention(exc):
        raise exc
    logger.warning(
        "database contention on %s %s: sqlstate %s (%s)",
        request.method,
        request.url.path,
        getattr(getattr(exc, "orig", None), "sqlstate", None),
        type(exc).__name__,
    )
    return _problem_response(busy(CONTENTION_DETAIL), request)


app = create_app()
