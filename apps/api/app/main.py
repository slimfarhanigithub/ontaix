"""FastAPI application entry point for the Ontaix API."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.routers import health

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the FastAPI application and mount every router."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.include_router(health.router)
    return application


app = create_app()
