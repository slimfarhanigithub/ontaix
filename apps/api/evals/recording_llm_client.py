"""A language model client that records every call it forwards, per case, against a budget.

The teach pipeline sees an ordinary `LlmClient`. Each case runs in its own asyncio task and
opens its own recording with `record_calls()`; the calls made while serving that case land in
that list, so cases can run concurrently against one shared client. Every call's cost is
charged to the run's `Budget`; once it is spent, calls are refused as a provider error that
names the budget, and no further case is started. A call the provider refuses with status 429
(its rate limit, a property of the deployment's quota, not of the model) is recorded and tried
again after a pause, up to RATE_LIMIT_RETRIES times, so a small quota does not turn into
comprehension failures; the recorded calls keep the refusals countable.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass

from app.clients.llm_client import (
    LlmAnswer,
    LlmCallError,
    LlmClient,
    LlmProviderError,
    LlmRequest,
)

BUDGET_REASON = "budget"
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_PAUSE_SECONDS = 15.0


@dataclass
class RecordedCall:
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_ms: int
    error: str | None = None


@dataclass
class Budget:
    """Euros a run may spend on model calls and OCR together."""

    cap_eur: float
    spent_eur: float = 0.0

    @property
    def exhausted(self) -> bool:
        return self.spent_eur >= self.cap_eur

    def charge(self, eur: float) -> None:
        self.spent_eur += eur


_calls: ContextVar[list[RecordedCall] | None] = ContextVar("eval_llm_calls", default=None)


def record_calls() -> list[RecordedCall]:
    """Start recording in the current task; returns the list the calls are appended to."""
    calls: list[RecordedCall] = []
    _calls.set(calls)
    return calls


class RecordingLlmClient:
    def __init__(self, inner: LlmClient, budget: Budget) -> None:
        self.inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self._budget = budget

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return self.inner.estimate_input_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        calls = _calls.get()
        if self._budget.exhausted:
            if calls is not None:
                calls.append(RecordedCall(0, 0, 0.0, 0, BUDGET_REASON))
            raise LlmProviderError(BUDGET_REASON)
        attempt = 0
        while True:
            try:
                answer = await self.inner.complete(request)
                break
            except LlmCallError as exc:
                self._budget.charge(exc.cost_eur)
                limited = _rate_limited(exc)
                if calls is not None:
                    calls.append(
                        RecordedCall(
                            exc.input_tokens,
                            exc.output_tokens,
                            exc.cost_eur,
                            exc.latency_ms,
                            f"{type(exc).__name__}: {'rate limited' if limited else exc}",
                        )
                    )
                if not limited or attempt >= RATE_LIMIT_RETRIES:
                    raise
            attempt += 1
            await asyncio.sleep(RATE_LIMIT_PAUSE_SECONDS * attempt)
        self._budget.charge(answer.cost_eur)
        if calls is not None:
            calls.append(
                RecordedCall(
                    answer.input_tokens, answer.output_tokens, answer.cost_eur, answer.latency_ms
                )
            )
        return answer


def _rate_limited(exc: LlmCallError) -> bool:
    """Whether the provider refused the call with status 429."""
    return getattr(exc.__cause__, "status_code", None) == 429
