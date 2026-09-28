"""The tenant decision lock, answered with 503 when it is not granted in time."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import proposal_repository
from app.repositories.proposal_repository import DecisionLockTimeoutError
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_DETAIL = "another decision of this tenant is still running; try again"


async def acquire(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Take the tenant's decision lock for the rest of the transaction, or answer 503."""
    try:
        await proposal_repository.lock_decisions(session, tenant_id)
    except DecisionLockTimeoutError as exc:
        logger.warning("decision lock of tenant %s not granted in time", tenant_id)
        raise ProblemError(503, "unavailable", LOCK_TIMEOUT_DETAIL) from exc
