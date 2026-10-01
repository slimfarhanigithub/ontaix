"""Database access for the `document_extraction_job` table.

Runners claim work with `FOR UPDATE SKIP LOCKED`, so two runners never claim one job. Every
later write of a runner is fenced: one `UPDATE ... WHERE id = $job AND lease_owner = $runner AND
lease_epoch = $epoch AND lease_until > clock_timestamp()`, compared at statement time; zero rows
means the lease is lost. The submit claim is one conditional `UPDATE ... RETURNING`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.document_extraction_job import DocumentExtractionJob as Job

ACTIVE_STATES = ("queued", "running")
FINAL_STATES = ("succeeded", "failed", "cancelled")
LEASE = timedelta(minutes=5)


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    import_id: uuid.UUID,
    company_id: uuid.UUID,
    chunks: int,
    token_ceiling: int,
    node_ceiling: int,
) -> Job:
    row = Job(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        import_id=import_id,
        company_id=company_id,
        chunks=chunks,
        token_ceiling=token_ceiling,
        node_ceiling=node_ceiling,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    return await session.scalar(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.id == job_id)
        .execution_options(populate_existing=True)
    )


async def get_by_id(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    return await session.scalar(
        select(Job).where(Job.id == job_id).execution_options(populate_existing=True)
    )


async def exists_for_import(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID
) -> bool:
    found = await session.scalar(
        select(Job.id).where(Job.tenant_id == tenant_id, Job.import_id == import_id)
    )
    return found is not None


async def import_ids_for_company(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> list[uuid.UUID]:
    """The document imports the company's extraction jobs were started from."""
    result = await session.scalars(
        select(Job.import_id).where(
            Job.tenant_id == tenant_id, Job.company_id == company_id, Job.import_id.is_not(None)
        )
    )
    return list(dict.fromkeys(result))


async def has_active(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(Job.id).where(
            Job.tenant_id == tenant_id,
            Job.actor_user_id == user_id,
            Job.state.in_(ACTIVE_STATES),
        )
    )
    return found is not None


async def cancel_queued(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """End a job no runner holds; False when it is claimed or already final."""
    ended = await session.scalar(
        update(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.id == job_id,
            Job.state == "queued",
            Job.lease_owner.is_(None),
        )
        .values(state="cancelled", cancel_requested=True, phase=None, finished_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    return ended is not None


async def request_cancel(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Ask the runner holding an active job to stop before its next model call."""
    await session.execute(
        update(Job)
        .where(Job.tenant_id == tenant_id, Job.id == job_id, Job.state.in_(ACTIVE_STATES))
        .values(cancel_requested=True)
        .execution_options(synchronize_session=False)
    )


async def claimable(session: AsyncSession) -> Job | None:
    """The oldest queued or orphaned job, row-locked; locked rows are skipped."""
    return await session.scalar(
        select(Job)
        .where(
            Job.state.in_(ACTIVE_STATES),
            or_(Job.lease_until.is_(None), Job.lease_until < func.now()),
        )
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


async def take_lease(session: AsyncSession, job: Job, runner: uuid.UUID) -> int:
    """Hold the locked job for `runner`: a new epoch, one more attempt, five minutes."""
    epoch = await session.scalar(
        update(Job)
        .where(Job.id == job.id)
        .values(
            lease_owner=runner,
            lease_epoch=Job.lease_epoch + 1,
            lease_until=func.now() + LEASE,
            attempts=Job.attempts + 1,
            state="running",
            phase=func.coalesce(Job.phase, "outline"),
            started_at=func.coalesce(Job.started_at, func.now()),
        )
        .execution_options(synchronize_session=False)
        .returning(Job.lease_epoch)
    )
    await session.refresh(job)
    return int(epoch)


async def fail_locked(session: AsyncSession, job: Job, reason: str) -> None:
    """End a locked job no runner holds as failed."""
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            state="failed",
            failure_reason=reason,
            phase=None,
            finished_at=func.now(),
            lease_owner=None,
            lease_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    await session.refresh(job)


async def cancel_locked(session: AsyncSession, job: Job) -> None:
    """End a locked job no runner holds as cancelled."""
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            state="cancelled",
            phase=None,
            finished_at=func.now(),
            lease_owner=None,
            lease_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    await session.refresh(job)


async def fenced_update(
    session: AsyncSession, job_id: uuid.UUID, runner: uuid.UUID, epoch: int, values: dict[str, Any]
) -> Job | None:
    """Write `values` and extend the lease by five minutes if `runner` still holds the lease of
    `epoch`; None when it does not."""
    return await _fenced(
        session, job_id, runner, epoch, {**values, "lease_until": func.clock_timestamp() + LEASE}
    )


async def fenced_finish(
    session: AsyncSession,
    job_id: uuid.UUID,
    runner: uuid.UUID,
    epoch: int,
    values: dict[str, Any],
    keep_result: timedelta | None,
) -> Job | None:
    """End the job with `values` if `runner` still holds the lease of `epoch`: the lease is
    cleared, `finished_at` is now and, for a result, `expires_at` is `keep_result` later."""
    changes: dict[str, Any] = {
        **values,
        "phase": None,
        "lease_owner": None,
        "lease_until": None,
        "finished_at": func.now(),
    }
    if keep_result is not None:
        changes["expires_at"] = func.now() + keep_result
    return await _fenced(session, job_id, runner, epoch, changes)


async def claim_submit(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Mark a succeeded job submitted unless it was submitted already or has expired."""
    claimed = await session.scalar(
        update(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.id == job_id,
            Job.submitted_at.is_(None),
            Job.state == "succeeded",
            Job.expires_at > func.now(),
        )
        .values(submitted_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    return claimed is not None


async def delete_expired(session: AsyncSession, now: datetime) -> int:
    """Delete results expired more than 24 hours ago, and failed or cancelled jobs 48 hours
    after they finished."""
    result = await session.execute(
        delete(Job).where(
            or_(
                Job.expires_at < now - timedelta(hours=24),
                and_(
                    Job.state.in_(("failed", "cancelled")),
                    Job.finished_at < now - timedelta(hours=48),
                ),
            )
        )
    )
    return result.rowcount or 0


async def _fenced(
    session: AsyncSession, job_id: uuid.UUID, runner: uuid.UUID, epoch: int, changes: dict[str, Any]
) -> Job | None:
    result = await session.scalar(
        update(Job)
        .where(
            and_(
                Job.id == job_id,
                Job.lease_owner == runner,
                Job.lease_epoch == epoch,
                Job.lease_until > func.clock_timestamp(),
            )
        )
        .values(**changes)
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    if result is None:
        return None
    return await get_by_id(session, job_id)
