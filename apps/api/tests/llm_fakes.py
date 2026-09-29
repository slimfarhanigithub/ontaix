"""A language model client for tests: recorded answers in, no network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.clients.llm_client import (
    LlmAnswer,
    LlmCallError,
    LlmRequest,
    estimate_tokens,
)

FIXTURES = Path(__file__).parent / "fixtures" / "llm"
INPUT_TOKENS = 812
OUTPUT_TOKENS = 64


def recorded(name: str) -> str:
    """A recorded model answer from tests/fixtures/llm, as the raw JSON text."""
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


class FakeLlmClient:
    provider = "fake"
    model = "fake-model-1"

    def __init__(self) -> None:
        # An answer is recorded text, an error to raise, or a builder that writes the answer
        # from the request's JSON data, so it can cite the handles that request sent.
        self.answers: list[str | LlmCallError | Callable[[dict], str]] = []
        self.requests: list[LlmRequest] = []

    def answer(self, *answers: str | LlmCallError | Callable[[dict], str]) -> FakeLlmClient:
        self.answers.extend(answers)
        return self

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        self.requests.append(request)
        if not self.answers:
            raise AssertionError("the fake model has no recorded answer left")
        answer = self.answers.pop(0)
        if isinstance(answer, LlmCallError):
            raise answer
        if callable(answer):
            answer = answer(json.loads(request.user))
        return LlmAnswer(answer, INPUT_TOKENS, OUTPUT_TOKENS, 0.002094, 420)

    def context(self, index: int = -1) -> dict:
        """The JSON data of a request's user message."""
        return json.loads(self.requests[index].user)
