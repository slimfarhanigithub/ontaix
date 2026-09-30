"""Bounded retries of a language model call the provider refuses with 429 or 503.

A provider that rate-limits (429) or is briefly unavailable (503) has processed no tokens, so a
retry costs nothing and each client call still settles once: the caller's reservation covers
the whole call, retries included, and only the answering attempt reports tokens. A call is
tried at most `MAX_RETRIES` more times. The wait before a retry is the provider's
`retry-after-ms` or `retry-after`, capped at `RETRY_AFTER_CAP_SECONDS`, else an exponential
backoff with jitter. A retry is made only when, after its wait, at least `MIN_ATTEMPT_SECONDS`
of the call's wall-clock budget remain; otherwise the refusal is raised at once, so a retry
never stretches the call past its timeout. Logs carry the status, the retry count and the wait,
never a prompt, an answer or a header value other than the wait.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({429, 503})
MAX_RETRIES = 2
RETRY_AFTER_CAP_SECONDS = 4.0
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 4.0
# A retry with less time than this left before the deadline would only end as a timeout.
MIN_ATTEMPT_SECONDS = 1.0


async def call_with_retries[T](
    attempt: Callable[[float], Awaitable[T]],
    deadline: float,
    status_error: type[Exception],
) -> T:
    """The result of `attempt(remaining_seconds)`, tried again while it raises a
    `status_error` whose `status_code` is 429 or 503, within the bounds above.

    `deadline` is a `time.monotonic()` value: the end of the call's wall-clock budget. The
    last refusal is raised unchanged when no retry is left or none fits before the deadline.
    """
    retries = 0
    first = time.monotonic()
    while True:
        started = time.monotonic()
        try:
            result = await attempt(max(deadline - started, 0.0))
        except status_error as exc:
            status = getattr(exc, "status_code", None)
            logger.debug(
                "language model attempt %d answered %s after %d ms",
                retries + 1,
                status,
                _ms_since(started),
            )
            if status not in RETRYABLE_STATUSES or retries >= MAX_RETRIES:
                raise
            wait = retry_wait(_headers(exc), retries)
            if deadline - time.monotonic() - wait < MIN_ATTEMPT_SECONDS:
                logger.info(
                    "language model call answered %s; no retry fits in the time left", status
                )
                raise
            retries += 1
            logger.info(
                "language model call answered %s; retry %d of %d in %.2f s",
                status,
                retries,
                MAX_RETRIES,
                wait,
            )
            await asyncio.sleep(wait)
            continue
        logger.debug(
            "language model attempt %d answered after %d ms, %d ms in all",
            retries + 1,
            _ms_since(started),
            _ms_since(first),
        )
        return result


def retry_wait(headers: Mapping[str, str], retries: int) -> float:
    """Seconds to wait before retry number `retries + 1`: the provider's hint, capped, else
    an exponential backoff with jitter between half and all of its ceiling."""
    hinted = retry_after_seconds(headers)
    if hinted is not None:
        return min(hinted, RETRY_AFTER_CAP_SECONDS)
    ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2**retries)
    return random.uniform(ceiling / 2, ceiling)


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """The wait the provider asks for, from `retry-after-ms` (milliseconds) or `retry-after`
    (seconds or an HTTP date); None when neither is present and readable."""
    millis = _number(headers.get("retry-after-ms"))
    if millis is not None:
        return max(millis / 1000, 0.0)
    value = headers.get("retry-after")
    seconds = _number(value)
    if seconds is not None:
        return max(seconds, 0.0)
    if not value:
        return None
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


def _headers(exc: Exception) -> Mapping[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    return headers if headers is not None else {}


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _ms_since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
