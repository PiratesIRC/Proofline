"""One structured-output request to the Claude API.

AnthropicBackend wraps the official anthropic SDK; tests replace it with any object that has
the same send() method. It runs on a worker thread (see ai_service) and never logs the text.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 8000
TIMEOUT_SECONDS = 20.0
EFFORT = "low"

AUTH_MESSAGE = "The Claude API did not accept the API key."
RATE_LIMIT_MESSAGE = "The Claude API is limiting requests. Try again in a minute."
TIMEOUT_MESSAGE = "Claude took longer than 20 seconds. Try again."
NETWORK_MESSAGE = "Could not reach the Claude API."
SERVER_MESSAGE = "The Claude API had a problem. Try again."
REFUSAL_MESSAGE = "Claude declined this request."
CUT_OFF_MESSAGE = "Claude's answer was cut off."
BAD_RESPONSE_MESSAGE = "Claude's answer could not be read."


@dataclass(frozen=True)
class AiRequest:
    job: str  # recorded in the usage ledger: "rephrase", "rewrite", "tone", "issues", "test"
    system: str
    text: str
    schema: dict
    max_tokens: int


@dataclass(frozen=True)
class AiResult:
    data: dict
    input_tokens: int
    output_tokens: int


@dataclass
class AiError(Exception):
    """A failed request. kind is one of auth, rate_limit, rejected, network, timeout, server,
    refusal, bad_response; token counts are set when the API reported them."""

    kind: str
    message: str
    input_tokens: int | None = field(default=None)
    output_tokens: int | None = field(default=None)

    def __str__(self) -> str:
        return self.message


class AiBackend(Protocol):
    def send(self, request: AiRequest, model: str) -> AiResult: ...


class AnthropicBackend:
    def __init__(self, api_key: str) -> None:
        import anthropic  # imported here so app start-up does not load the SDK

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)

    def send(self, request: AiRequest, model: str) -> AiResult:
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.text}],
                output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": request.schema}},
            )
        except self._anthropic.APIError as exc:
            raise self._error_for(exc) from exc
        return result_from(response)

    def _error_for(self, exc: Exception) -> AiError:
        a = self._anthropic
        if isinstance(exc, (a.AuthenticationError, a.PermissionDeniedError)):
            return AiError("auth", AUTH_MESSAGE)
        if isinstance(exc, a.RateLimitError):
            return AiError("rate_limit", RATE_LIMIT_MESSAGE)
        if isinstance(exc, a.APITimeoutError):
            return AiError("timeout", TIMEOUT_MESSAGE)
        if isinstance(exc, a.APIConnectionError):
            return AiError("network", NETWORK_MESSAGE)
        if isinstance(exc, a.APIStatusError) and 400 <= exc.status_code < 500:
            return AiError("rejected", rejected_message(exc.status_code, getattr(exc, "body", None)))
        return AiError("server", SERVER_MESSAGE)


def rejected_message(status: int, body: Any) -> str:
    """The API's own explanation for a 4xx (say, a low credit balance), or the status code."""
    detail = body.get("error", {}).get("message") if isinstance(body, dict) else None
    if isinstance(detail, str) and detail.strip():
        return f"The Claude API refused the request: {detail.strip()}"
    return f"The Claude API refused the request (HTTP {status})."


def result_from(response: Any) -> AiResult:
    """Parse a messages.create response; raises AiError carrying the token counts on failure."""
    tokens = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        raise AiError("refusal", REFUSAL_MESSAGE, **tokens)
    if response.stop_reason == "max_tokens":
        raise AiError("bad_response", CUT_OFF_MESSAGE, **tokens)
    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        data = json.loads(text) if text is not None else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        log.warning("Claude returned no readable JSON object (stop reason %s)", response.stop_reason)
        raise AiError("bad_response", BAD_RESPONSE_MESSAGE, **tokens)
    return AiResult(data, **tokens)
