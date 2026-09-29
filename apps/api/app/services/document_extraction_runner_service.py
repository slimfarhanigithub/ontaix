"""The runner of whole-document extraction jobs, inside the API process.

A runner claims the oldest queued or orphaned job with `FOR UPDATE SKIP LOCKED` and takes its
lease: a new epoch, one more attempt, five minutes. A job past its attempt limit fails instead.
The runner then reads the import's sentences, cuts them into chunks and runs pass 1 (outline)
and pass 2 (sections) chunk by chunk from the first unfinished chunk, so a job whose runner died
resumes where it stopped. No transaction is open during a model call; the lease is renewed
while the call runs and while mapping runs, and every write after the claim - progress, outline,
tokens, the final state and the `extraction.changed` row - is fenced on the lease, so a runner
that lost it stops without writing more, settling only its own token reservation.

A chunk whose answer is invalid, timed out, refused or failed is listed as unresolved and the
job goes on. The job stops calling the model at its token ceiling, the tenant's monthly cap,
its time limit or a cancellation; it then maps what it has. It fails when the model is not
configured, the cap is 0, the import is gone or nothing could be drafted.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.document_extraction import (
    OUTLINE_MAX_OUTPUT_TOKENS,
    OUTLINE_SCHEMA,
    OUTLINE_SYSTEM_PROMPT,
    SECTION_MAX_OUTPUT_TOKENS,
    SECTION_SCHEMA,
    SECTION_SYSTEM_PROMPT,
)
from app.clients.db_client import get_session_factory
from app.clients.llm_client import (
    LlmAnswer,
    LlmCallError,
    LlmClient,
    LlmRefused,
    LlmRequest,
    LlmTimeout,
    get_llm_client,
)
from app.config import LlmProfile, Settings, get_settings
from app.models.api.settings import DEFAULT_LLM_MONTHLY_TOKEN_CAP
from app.models.storage.document_extraction_job import DocumentExtractionJob
from app.repositories import (
    document_extraction_job_repository,
    document_import_repository,
    document_import_sentence_repository,
)
from app.repositories.llm_call_repository import CallRecord
from app.services import import_service, llm_usage_service
from app.services.document_extraction_mapping_service import map_tree
from app.services.document_extraction_pass_service import (
    Chunk,
    ChunkResult,
    InvalidAnswer,
    Outline,
    Sentence,
    context,
    read_outline_answer,
    read_section_answer,
    select_handles,
    unresolved_chunk,
)
from app.services.extraction_event_service import emit_changed
from app.services.ontology_view_service import OntologyView, load_view
from app.utilities.chunking import chunk_bounds
from app.utilities.clock import get_clock

logger = logging.getLogger(__name__)

DEEP: LlmProfile = "deep"


RENEW_SECONDS = 60.0
MAX_UNRESOLVED = 5000
RESULT_KEPT = timedelta(hours=24)

_wake: asyncio.Event | None = None


class _LeaseLost(Exception):
    """Another runner holds the job now; this one stops without writing."""


class _Stop(Exception):
    """The job stops calling the model; `reason` is listed for every unread chunk."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _Lease:
    runner: uuid.UUID
    epoch: int


async def run_periodically(poll_seconds: float) -> None:
    """Run jobs until cancelled: one after another while there is work, then wait for a new
    job or `poll_seconds`."""
    global _wake
    _wake = asyncio.Event()
    runner = uuid.uuid4()
    while True:
        try:
            ran = await run_once(runner)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("the extraction runner failed; retrying in %.0f s", poll_seconds)
            ran = False
        if ran:
            continue
        _wake.clear()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_wake.wait(), poll_seconds)


def wake() -> None:
    """A job was queued: the runner of this process looks for it now."""
    if _wake is not None:
        _wake.set()


async def run_once(runner: uuid.UUID | None = None) -> bool:
    """Claim one job and run it to its end or until its lease is lost; False when no job
    was waiting."""
    runner = runner or uuid.uuid4()
    claimed = await _claim(runner)
    if claimed is None:
        return False
    job, epoch = claimed
    if epoch is None:
        return True
    run = _Run(job, _Lease(runner, epoch), get_settings())
    try:
        await run.execute()
    except _LeaseLost:
        logger.warning("extraction job %s: lease lost; another runner continues it", job.id)
    return True


async def _claim(runner: uuid.UUID) -> tuple[DocumentExtractionJob, int | None] | None:
    """The claimed job and its lease epoch; epoch None when the claim ended the job instead."""
    max_attempts = get_settings().document_extraction_max_attempts
    async with get_session_factory()() as session:
        job = await document_extraction_job_repository.claimable(session)
        if job is None:
            return None
        epoch: int | None = None
        if job.cancel_requested:
            await document_extraction_job_repository.cancel_locked(session, job)
        elif job.attempts + 1 > max_attempts:
            await document_extraction_job_repository.fail_locked(session, job, "too_many_attempts")
        else:
            epoch = await document_extraction_job_repository.take_lease(session, job, runner)
        await emit_changed(session, job)
        await session.commit()
        return job, epoch


class _Run:
    def __init__(self, job: DocumentExtractionJob, lease: _Lease, settings: Settings) -> None:
        self.job = job
        self.lease = lease
        self.settings = settings
        self.deadline = (job.started_at or get_clock().now()) + timedelta(
            minutes=settings.document_extraction_job_timeout_minutes
        )
        self.entries: list[dict[str, Any]] = list(job.outline)
        self.unresolved: list[dict[str, Any]] = list(job.unresolved)
        self.tokens_used = int(job.tokens_used)
        self.degraded = bool(job.degraded)
        self.calls = 0

    async def execute(self) -> None:
        try:
            await self._execute()
        except (_LeaseLost, asyncio.CancelledError):
            raise
        except Exception:
            logger.exception("extraction job %s failed", self.job.id)
            await self._finish({"state": "failed", "failure_reason": "internal"})

    async def _execute(self) -> None:
        job = self.job
        sentences, details = await self._sentences()
        if sentences is None:
            await self._finish({"state": "failed", "failure_reason": "import_expired"})
            return
        chunks = [
            Chunk(n, sentences[first:end])
            for n, (first, end) in enumerate(
                chunk_bounds(
                    [len(s.text) for s in sentences],
                    self.settings.document_extraction_chunk_chars,
                )
            )
        ]
        if len(chunks) != job.chunks:
            await self._write({"chunks": len(chunks)})
        client = get_llm_client(DEEP)
        view = await self._view()
        cap = (
            view.settings.llm_monthly_token_cap if view.settings else DEFAULT_LLM_MONTHLY_TOKEN_CAP
        )
        pending = job.outline_chunks_done < len(chunks) or job.section_chunks_done < len(chunks)
        if pending and client is None:
            await self._finish({"state": "failed", "failure_reason": "not_configured"})
            return
        if pending and cap <= 0:
            await self._finish({"state": "failed", "failure_reason": "budget_exhausted"})
            return
        company = view.companies.get(job.company_id)
        if company is None or view.root_of(job.company_id) is None:
            await self._finish({"state": "failed", "failure_reason": "internal"})
            return
        stopped: str | None = None
        try:
            for chunk in chunks[job.outline_chunks_done :]:
                await self._chunk(client, view, company.name, chunk, len(chunks), "outline", cap)
                await self._progress({"outline_chunks_done": chunk.number + 1, "phase": "outline"})
            await self._progress({"phase": "sections"})
            for chunk in chunks[self.job.section_chunks_done :]:
                await self._chunk(client, view, company.name, chunk, len(chunks), "section", cap)
                await self._progress({"section_chunks_done": chunk.number + 1})
        except _Stop as stop:
            stopped = stop.reason
            if stop.reason == "cancelled":
                await self._finish({"state": "cancelled"})
                return
            self.degraded = True
            for chunk in chunks[self.job.section_chunks_done :]:
                self._add_unresolved([unresolved_chunk(chunk, stop.reason)])
            await self._progress(
                {"outline_chunks_done": len(chunks), "section_chunks_done": len(chunks)}
            )
        await self._map(details, stopped)

    async def _chunk(
        self,
        client: LlmClient | None,
        view: OntologyView,
        company_name: str,
        chunk: Chunk,
        total: int,
        pass_name: str,
        cap: int,
    ) -> None:
        """One model call for one chunk; its outcome is added to the job's state in memory."""
        if self.job.cancel_requested:
            raise _Stop("cancelled")
        if get_clock().now() >= self.deadline:
            raise _Stop("job_timeout")
        assert client is not None
        outline = Outline(view, self.job.company_id, self.entries)
        handles = select_handles(
            outline, chunk, self.settings.document_extraction_outline_context_nodes
        )
        outline_pass = pass_name == "outline"
        bound = OUTLINE_MAX_OUTPUT_TOKENS if outline_pass else SECTION_MAX_OUTPUT_TOKENS
        request = LlmRequest(
            system=OUTLINE_SYSTEM_PROMPT if outline_pass else SECTION_SYSTEM_PROMPT,
            user=context(
                outline,
                handles,
                chunk,
                total,
                company_name,
                "outline" if outline_pass else "section",
            ),
            output_schema=OUTLINE_SCHEMA if outline_pass else SECTION_SCHEMA,
            max_output_tokens=bound + self.settings.llm_profile(DEEP).reasoning_allowance_tokens,
            timeout_seconds=self.settings.document_extraction_timeout_seconds,
        )
        upper = client.estimate_input_tokens(request) + request.max_output_tokens
        if self.tokens_used + upper > self.job.token_ceiling:
            raise _Stop("budget_exhausted")
        reservation = await llm_usage_service.reserve(self.job.tenant_id, upper, cap)
        if reservation is None:
            raise _Stop("budget_exhausted")
        self.calls += 1
        outcome, usage = "invalid_output", (0, 0, 0.0, 0)
        result: ChunkResult | None = None
        outline_mark = outline.mark()
        try:
            try:
                answer = await self._complete_renewing(client, request)
            except LlmCallError as exc:
                usage = (exc.input_tokens, exc.output_tokens, exc.cost_eur, exc.latency_ms)
                if isinstance(exc, LlmTimeout):
                    outcome = "timeout"
                elif isinstance(exc, LlmRefused):
                    outcome = "refused"
                else:
                    outcome = "provider_error"
            else:
                usage = (
                    answer.input_tokens,
                    answer.output_tokens,
                    answer.cost_eur,
                    answer.latency_ms,
                )
                read = read_outline_answer if outline_pass else read_section_answer
                try:
                    result = read(answer.text, outline, handles, chunk)
                    outcome = "used"
                except InvalidAnswer as exc:
                    outline.rollback(outline_mark)
                    logger.info(
                        "extraction job %s: chunk %d refused: %s", self.job.id, chunk.number, exc
                    )
        except BaseException:
            outline.rollback(outline_mark)
            raise
        finally:
            self.tokens_used += usage[0] + usage[1]
            await self._settle(client, reservation, outcome, usage)
        if result is None:
            self.degraded = True
            reason = "model_invalid_output" if outcome == "invalid_output" else outcome
            self._add_unresolved([unresolved_chunk(chunk, reason)])
            return
        self._add_unresolved(result.unresolved)

    async def _complete_renewing(self, client: LlmClient, request: LlmRequest) -> LlmAnswer:
        """The model call, with the lease renewed every minute while it runs."""
        return await self._renewing(client.complete(request))

    async def _renewing[T](self, work: Awaitable[T]) -> T:
        """`work`, with the lease renewed every `RENEW_SECONDS` while it runs; a lost lease
        cancels it."""
        call = asyncio.ensure_future(work)
        try:
            while True:
                done, _ = await asyncio.wait({call}, timeout=RENEW_SECONDS)
                if done:
                    return call.result()
                await self._write({})
        finally:
            if not call.done():
                call.cancel()
                with contextlib.suppress(BaseException):
                    await call

    async def _settle(
        self,
        client: LlmClient,
        reservation: llm_usage_service.Reservation,
        outcome: str,
        usage: tuple[int, int, float, int],
    ) -> None:
        record = CallRecord(
            tenant_id=self.job.tenant_id,
            actor_kind="user",
            actor_id=self.job.actor_user_id,
            company_id=self.job.company_id,
            purpose=llm_usage_service.DOCUMENT_EXTRACTION,
            provider=client.provider,
            model=client.model,
            input_tokens=usage[0],
            output_tokens=usage[1],
            cost_eur=usage[2],
            latency_ms=usage[3],
            outcome=outcome,
        )
        try:
            await llm_usage_service.settle(reservation, record)
        except Exception:
            logger.exception("settling a language model call failed; its reservation stays")

    async def _map(self, details: dict[int, dict[str, Any]], stopped: str | None) -> None:
        await self._progress({"phase": "mapping"})
        view = await self._view()
        # Mapping runs in a worker thread so the lease is renewed while it works.
        mapped = await self._renewing(
            asyncio.to_thread(
                map_tree, view, self.job.company_id, self.entries, details, self.job.node_ceiling
            )
        )
        self._add_unresolved(mapped.unresolved)
        self.degraded = self.degraded or mapped.degraded
        if not mapped.drafts:
            if stopped == "job_timeout":
                reason = "job_timeout"
            elif self.calls == 0 and stopped == "budget_exhausted":
                reason = "budget_exhausted"
            else:
                reason = "no_drafts"
            await self._finish({"state": "failed", "failure_reason": reason})
            return
        await self._finish(
            {
                "state": "succeeded",
                "drafts": mapped.drafts,
                "notes": mapped.notes,
                "draft_count": len(mapped.drafts),
            }
        )

    async def _sentences(
        self,
    ) -> tuple[list[Sentence] | None, dict[int, dict[str, Any]]]:
        """The import's sentences and each one's `originDetail`; None when the import is gone."""
        job = self.job
        if job.import_id is None:
            return None, {}
        async with get_session_factory()() as session:
            row = await document_import_repository.get(session, job.tenant_id, job.import_id)
            if row is None:
                return None, {}
            rows = await document_import_sentence_repository.list_for_import(
                session, job.tenant_id, job.import_id
            )
        sentences = [Sentence(i, r.text) for i, r in enumerate(rows)]
        details = {i: import_service.origin_detail(row, i, r) for i, r in enumerate(rows)}
        return (sentences or None), details

    async def _view(self) -> OntologyView:
        async with get_session_factory()() as session:
            return await load_view(session, self.job.tenant_id)

    async def _progress(self, values: dict[str, Any]) -> None:
        """Write the job's state so far with `values`, and its event; fenced."""
        await self._write(
            {
                **values,
                "outline": self.entries,
                "unresolved": self.unresolved,
                "tokens_used": self.tokens_used,
                "degraded": self.degraded,
            },
            event=True,
        )

    async def _finish(self, values: dict[str, Any]) -> None:
        """End the job: its final state, the lease cleared, and its event; fenced."""
        final = {
            **values,
            "outline": self.entries,
            "unresolved": self.unresolved,
            "tokens_used": self.tokens_used,
            "degraded": self.degraded,
        }
        keep = RESULT_KEPT if values["state"] == "succeeded" else None
        async with get_session_factory()() as session:
            job = await document_extraction_job_repository.fenced_finish(
                session, self.job.id, self.lease.runner, self.lease.epoch, final, keep
            )
            await self._commit(session, job, event=True)

    async def _write(self, values: dict[str, Any], *, event: bool = False) -> None:
        """Write `values` and renew the lease; fenced."""
        async with get_session_factory()() as session:
            job = await document_extraction_job_repository.fenced_update(
                session, self.job.id, self.lease.runner, self.lease.epoch, values
            )
            await self._commit(session, job, event=event)

    async def _commit(
        self, session: AsyncSession, job: DocumentExtractionJob | None, *, event: bool
    ) -> None:
        """Commit a fenced write with its event, or stop when the lease was lost."""
        if job is None:
            await session.rollback()
            raise _LeaseLost(str(self.job.id))
        if event:
            await emit_changed(session, job)
        await session.commit()
        self.job = job

    def _add_unresolved(self, items: list[dict[str, Any]]) -> None:
        room = MAX_UNRESOLVED - len(self.unresolved)
        if room > 0:
            self.unresolved.extend(items[:room])
