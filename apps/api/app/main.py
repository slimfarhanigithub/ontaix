"""FastAPI application entry point for the Ontaix API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import DEV_USER_HEADER
from app.clients.db_client import dispose_engine
from app.config import get_settings
from app.routers import (
    audit,
    companies,
    concepts,
    domain_products,
    health,
    proposals,
    relations,
    scene,
)
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
PROBLEM_MEDIA_TYPE = "application/problem+json"
HTTP_STATUS_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found"}


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI application and mount every router under /api/v1."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.is_dev:
        logger.warning(
            "environment is dev: the %s header is accepted without any other credential",
            DEV_USER_HEADER,
        )

    application = FastAPI(title=settings.app_name, version="1.0.0", lifespan=_lifespan)
    application.include_router(health.router)
    for module in (scene, companies, domain_products, concepts, relations, proposals, audit):
        application.include_router(module.router, prefix=API_PREFIX)
    application.include_router(health.router, prefix=API_PREFIX)

    application.add_exception_handler(ProblemError, _problem_handler)
    application.add_exception_handler(RequestValidationError, _validation_handler)
    application.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    return application


def _problem_response(problem: ProblemError, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.body(request.url.path),
        media_type=PROBLEM_MEDIA_TYPE,
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


app = create_app()
