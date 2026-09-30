"""A language model client for tests: recorded answers in, no network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.clients.llm_client import (
    LlmAnswer,
    LlmCallError,
    LlmRequest,
    TextListener,
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
        # A streamed answer arrives in fragments of this many characters; with `restart_at`
        # set, a first attempt stops after that many characters and the answer starts again,
        # as a retried attempt does.
        self.fragment = 9
        self.restart_at: int | None = None
        self.streamed = 0

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

    async def stream(self, request: LlmRequest, on_text: TextListener) -> LlmAnswer:
        answer = await self.complete(request)
        self.streamed += 1
        text = answer.text
        if self.restart_at is not None:
            for end in range(self.fragment, self.restart_at, self.fragment):
                await on_text(text[:end])
        for end in range(self.fragment, len(text) + self.fragment, self.fragment):
            await on_text(text[:end])
        return answer

    def answer_text(self, raw: str, request: LlmRequest) -> str:
        return raw

    def context(self, index: int = -1) -> dict:
        """The JSON data of a request's user message."""
        return json.loads(self.requests[index].user)
