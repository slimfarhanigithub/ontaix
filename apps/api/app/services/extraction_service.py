"""Runs document extraction in a child process with a wall-clock limit.

Extraction is CPU-bound and its cost depends on the uploaded bytes, so it never runs on the
event loop: each job starts a fresh process, the request waits for it in a thread, and a job
still running at the limit is terminated and answered as too large. A crash of the child is
answered as an unreadable document. At most `extraction_concurrency` children run at once in a
process; a job arriving while every slot is taken is refused at once with `503 busy`, and each
child's address space is capped on Linux.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import sys
from multiprocessing.connection import Connection

from app.config import get_settings
from app.utilities.document_text import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    Sentence,
    extract_sentences,
)
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

EXTRACTION_TIMEOUT_SECONDS = 20.0
BUSY_RETRY_AFTER_SECONDS = 5

_TOO_LARGE = "too_large"
_UNREADABLE = "unreadable"
_OK = "ok"

_slots: tuple[int, asyncio.Semaphore] | None = None


async def extract(data: bytes, media_type: str) -> tuple[list[Sentence], int, int]:
    """The sentences of a document, its extracted characters and the number of text pieces left
    out, read in a child process.

    Raises `DocumentTooLargeError` past a limit or past `EXTRACTION_TIMEOUT_SECONDS`, and
    `DocumentUnreadableError` when the document cannot be read, and `503 busy` when every
    extraction slot is taken.
    """
    slots = _semaphore()
    if slots.locked():
        raise ProblemError(
            503,
            "busy",
            "every document extraction slot is in use; try again shortly",
            headers={"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)},
        )
    async with slots:
        memory = get_settings().extraction_memory_limit_bytes
        return await asyncio.to_thread(_run, data, media_type, EXTRACTION_TIMEOUT_SECONDS, memory)


def _semaphore() -> asyncio.Semaphore:
    """The process-wide extraction slots, rebuilt when the configured limit changes."""
    global _slots
    limit = get_settings().extraction_slots()
    if _slots is None or _slots[0] != limit:
        _slots = (limit, asyncio.Semaphore(limit))
    return _slots[1]


def _run(
    data: bytes, media_type: str, timeout: float, memory_limit: int
) -> tuple[list[Sentence], int, int]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_child, args=(sender, data, media_type, memory_limit), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            logger.warning("extraction of a %s document passed %.0f s", media_type, timeout)
            raise DocumentTooLargeError(f"the document takes longer than {timeout:.0f} s to read")
        try:
            status, payload = receiver.recv()
        except EOFError as exc:
            raise DocumentUnreadableError("the document could not be read") from exc
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        process.close()
    if status == _TOO_LARGE:
        raise DocumentTooLargeError(payload)
    if status == _UNREADABLE:
        raise DocumentUnreadableError(payload)
    sentences, extracted, skipped = payload
    return [Sentence(*s) for s in sentences], extracted, skipped


def _child(sender: Connection, data: bytes, media_type: str, memory_limit: int) -> None:
    """Child process entry: cap the address space, extract, and send one result tuple back."""
    _limit_memory(memory_limit)
    try:
        sentences, extracted, skipped = extract_sentences(data, media_type)
        rows = [(s.text, s.unit, s.index) for s in sentences]
        sender.send((_OK, (rows, extracted, skipped)))
    except DocumentTooLargeError as exc:
        sender.send((_TOO_LARGE, str(exc)))
    except DocumentUnreadableError as exc:
        sender.send((_UNREADABLE, str(exc)))
    except Exception:
        sender.send((_UNREADABLE, "the document could not be read"))
    finally:
        sender.close()


def _limit_memory(limit: int) -> None:
    """Cap the child's address space so one document cannot exhaust the host's memory; past
    it an allocation fails and the document is answered as unreadable. Windows has no
    `RLIMIT_AS`, so there the cap is skipped and only the time limit and slot count apply."""
    if sys.platform == "win32" or limit <= 0:
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
