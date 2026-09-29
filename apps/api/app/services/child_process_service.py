"""Runs untrusted-file parsing in a child process with a wall-clock limit and a memory cap.

Parsing an upload is CPU-bound and its cost depends on the uploaded bytes, so it never runs on
the event loop: each job starts a fresh process, the request waits for it in a thread, and a
job still running at the limit is terminated and answered as too large. The child starts in
`child_process_entry`, which blocks the network and caps the address space (on Linux) before
the job is unpickled, so a parser can neither exhaust the host's memory nor reach the network.
A crash of the child is answered as an unreadable file. At most `extraction_concurrency`
children run at once in a process, shared by document extraction and ontology parsing; a job
arriving while every slot is taken is refused at once with `503 busy`.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import pickle
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.services import child_process_entry
from app.utilities.document_errors import DocumentTooLargeError, DocumentUnreadableError
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

BUSY_RETRY_AFTER_SECONDS = 5


_slots: tuple[int, asyncio.Semaphore] | None = None


async def run(target: Callable[..., Any], args: tuple[Any, ...], timeout: float, what: str) -> Any:
    """`target(*args)` in a child process; `target` is a module-level function and its result
    is picklable.

    Raises `DocumentTooLargeError` past `timeout` seconds or the memory cap, the child's own
    `DocumentTooLargeError`, `DocumentUnreadableError` or `UnsupportedDocumentError`,
    `DocumentUnreadableError` when the child fails otherwise, and `503 busy` when every slot is
    taken. `what` names the file in messages and logs, never its content.
    """
    slots = _semaphore()
    if slots.locked():
        raise ProblemError(
            503,
            "busy",
            "every file reading slot is in use; try again shortly",
            headers={"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)},
        )
    async with slots:
        memory = get_settings().extraction_memory_limit_bytes
        return await asyncio.to_thread(_run, target, args, timeout, memory, what)


def _semaphore() -> asyncio.Semaphore:
    """The process-wide reading slots, rebuilt when the configured limit changes."""
    global _slots
    limit = get_settings().extraction_slots()
    if _slots is None or _slots[0] != limit:
        _slots = (limit, asyncio.Semaphore(limit))
    return _slots[1]


def _run(
    target: Callable[..., Any],
    args: tuple[Any, ...],
    timeout: float,
    memory_limit: int,
    what: str,
) -> Any:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    # The job travels pickled, so the child unpickles it - and imports the parser - only after
    # its network is blocked.
    job = pickle.dumps((target, args))
    process = context.Process(
        target=child_process_entry.child_main, args=(sender, job, memory_limit), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            logger.warning("reading %s passed %.0f s", what, timeout)
            raise DocumentTooLargeError(f"{what} takes longer than {timeout:.0f} s to read")
        try:
            status, payload = receiver.recv()
        except EOFError as exc:
            raise DocumentUnreadableError(f"{what} could not be read") from exc
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        process.close()
    if status == child_process_entry.REFUSED:
        raise payload
    return payload
