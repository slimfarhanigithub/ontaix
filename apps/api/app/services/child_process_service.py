"""Runs untrusted-file parsing in a child process with a wall-clock limit and a memory cap.

Parsing an upload is CPU-bound and its cost depends on the uploaded bytes, so it never runs on
the event loop: each job starts a fresh process, the request waits for it in a thread, and a
job still running at the limit is terminated and answered as too large. In the child the
address space is capped on Linux and every socket call fails, so a parser can neither exhaust
the host's memory nor reach the network. A crash of the child is answered as an unreadable
file. At most `extraction_concurrency` children run at once in a process, shared by document
extraction and ontology parsing; a job arriving while every slot is taken is refused at once
with `503 busy`.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import sys
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

from app.config import get_settings
from app.utilities.document_errors import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    UnsupportedDocumentError,
)
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

BUSY_RETRY_AFTER_SECONDS = 5

_OK = "ok"
_REFUSED = "refused"
_KNOWN_REFUSALS = (DocumentTooLargeError, DocumentUnreadableError, UnsupportedDocumentError)

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
    process = context.Process(target=_child, args=(sender, target, args, memory_limit), daemon=True)
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
    if status == _REFUSED:
        raise payload
    return payload


def _child(
    sender: Connection, target: Callable[..., Any], args: tuple[Any, ...], memory_limit: int
) -> None:
    """Child process entry: cap memory, cut the network, run, and send one result back."""
    _limit_memory(memory_limit)
    _refuse_network()
    try:
        sender.send((_OK, target(*args)))
    except _KNOWN_REFUSALS as exc:
        sender.send((_REFUSED, type(exc)(str(exc))))
    except MemoryError:
        sender.send((_REFUSED, DocumentTooLargeError("the file needs more memory than allowed")))
    except RecursionError:
        sender.send((_REFUSED, DocumentTooLargeError("the file nests too deeply")))
    except Exception:
        sender.send((_REFUSED, DocumentUnreadableError("the file could not be read")))
    finally:
        sender.close()


def _limit_memory(limit: int) -> None:
    """Cap the child's address space so one file cannot exhaust the host's memory; past it an
    allocation fails. Windows has no `RLIMIT_AS`, so there the cap is skipped and only the time
    limit and slot count apply."""
    if sys.platform == "win32" or limit <= 0:
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _refuse_network() -> None:
    """Every socket, connection and name lookup fails in the child: no parser fetches anything."""
    import socket

    def refuse(*_: object, **__: object) -> Any:
        raise OSError("network access is disabled while a file is read")

    socket.socket = refuse  # type: ignore[assignment,misc]
    socket.create_connection = refuse  # type: ignore[assignment]
    socket.getaddrinfo = refuse  # type: ignore[assignment]
