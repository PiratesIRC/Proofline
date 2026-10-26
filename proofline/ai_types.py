"""Request, result, error and backend types shared by every AI provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class AiRequest:
    job: str  # recorded in the usage ledger: "rephrase", "rewrite", "tone", "find_issues", "test"
    system: str
    text: str
    schema: dict
    max_tokens: int


@dataclass(frozen=True)
class AiResult:
    data: dict
    input_tokens: int
    output_tokens: int
    cost: float | None = None


@dataclass
class AiError(Exception):
    """A failed request. kind is one of auth, credit, rate_limit, rejected, network, timeout, server,
    refusal, bad_response; token counts are set when the API reported them."""

    kind: str
    message: str
    input_tokens: int | None = field(default=None)
    output_tokens: int | None = field(default=None)
    cut_off: bool = field(default=False)  # a bad_response because the answer hit max_tokens: never retried

    def __str__(self) -> str:
        return self.message


class AiBackend(Protocol):
    def send(self, request: AiRequest, model: str) -> AiResult: ...
