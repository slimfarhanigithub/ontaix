"""Runs document extraction in a child process with a wall-clock limit.

Extraction is CPU-bound and its cost depends on the uploaded bytes, so it never runs on the
event loop: each job starts a fresh process, the request waits for it in a thread, and a job
still running at the limit is terminated and answered as too large. A crash of the child is
answered as an unreadable document.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
from multiprocessing.connection import Connection

from app.utilities.document_text import (
    DocumentTooLargeError,
    DocumentUnreadableError,
    Sentence,
    extract_sentences,
)

logger = logging.getLogger(__name__)

EXTRACTION_TIMEOUT_SECONDS = 20.0

_TOO_LARGE = "too_large"
_UNREADABLE = "unreadable"
_OK = "ok"


async def extract(data: bytes, media_type: str) -> tuple[list[Sentence], int]:
    """The sentences of a document and its extracted characters, read in a child process.

    Raises `DocumentTooLargeError` past a limit or past `EXTRACTION_TIMEOUT_SECONDS`, and
    `DocumentUnreadableError` when the document cannot be read.
    """
    return await asyncio.to_thread(_run, data, media_type, EXTRACTION_TIMEOUT_SECONDS)


def _run(data: bytes, media_type: str, timeout: float) -> tuple[list[Sentence], int]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, data, media_type), daemon=True)
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
    if status == _TOO_LARGE:
        raise DocumentTooLargeError(payload)
    if status == _UNREADABLE:
        raise DocumentUnreadableError(payload)
    sentences, extracted = payload
    return [Sentence(*s) for s in sentences], extracted


def _child(sender: Connection, data: bytes, media_type: str) -> None:
    """Child process entry: extract and send one result tuple back."""
    try:
        sentences, extracted = extract_sentences(data, media_type)
        sender.send((_OK, ([(s.text, s.unit, s.index) for s in sentences], extracted)))
    except DocumentTooLargeError as exc:
        sender.send((_TOO_LARGE, str(exc)))
    except DocumentUnreadableError as exc:
        sender.send((_UNREADABLE, str(exc)))
    except Exception:
        sender.send((_UNREADABLE, "the document could not be read"))
    finally:
        sender.close()
