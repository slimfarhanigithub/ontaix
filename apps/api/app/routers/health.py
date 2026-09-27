"""Liveness endpoint used by container healthchecks and Kubernetes probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up. Carries no dependency checks."""
    return {"status": "ok"}
