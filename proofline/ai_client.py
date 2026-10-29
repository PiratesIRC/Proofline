"""One structured-output request to the Claude API.

AnthropicBackend wraps the official anthropic SDK; tests replace it with any object that has
the same send() method. It runs on a worker thread (see ai_service) and never logs the text.
The address is fixed and proxy environment variables are ignored (ai_http.make_client), so a
variable such as ANTHROPIC_BASE_URL cannot send the key elsewhere.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from proofline.ai_http import (
    DeadlineExceeded,
    error_for,
    make_client,
    message,
    run_within,
)
from proofline.ai_types import AiBackend, AiError, AiRequest, AiResult  # noqa: F401

log = logging.getLogger(__name__)

LABEL = "Claude"
BASE_URL = "https://api.anthropic.com"
MAX_INPUT_CHARS = 8000
TIMEOUT_SECONDS = 20.0
EFFORT = "low"
CREDIT_TEXT = "credit balance"  # the API's wording for an empty account, sent as 400 or 402
CREDIT_STATUSES = (400, 402)

AUTH_MESSAGE = message("auth", LABEL)
TIMEOUT_MESSAGE = message("timeout", LABEL, seconds=TIMEOUT_SECONDS)
REFUSAL_MESSAGE = message("refusal", LABEL)


class AnthropicBackend:
    def __init__(self, api_key: str) -> None:
        import anthropic  # imported here so app start-up does not load the SDK

        self._anthropic = anthropic
        self._api_key = api_key
        self._http = make_client(TIMEOUT_SECONDS)
        self._client = anthropic.Anthropic(
            api_key=api_key,
            base_url=BASE_URL,
            http_client=self._http,
            timeout=TIMEOUT_SECONDS,
            max_retries=0,
        )

    def send(self, request: AiRequest, model: str) -> AiResult:
        try:
            error = None
            try:
                # The SDK's timeout bounds each connect and read; run_within adds the total limit.
                response = run_within(lambda: self._create(request, model), TIMEOUT_SECONDS)
            except DeadlineExceeded:
                error = AiError("timeout", TIMEOUT_MESSAGE)
            except self._anthropic.APIError as exc:
                error = self._error_for(exc)  # the SDK exception holds the request; it is not kept
            if error is None:
                return result_from(response)
            raise error from None  # raised outside the except block, so no context is attached
        finally:
            self._http.close()

    def _create(self, request: AiRequest, model: str) -> Any:
        return self._client.messages.create(
            model=model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.text}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": request.schema}},
        )

    def _error_for(self, exc: Exception) -> AiError:
        a = self._anthropic
        if isinstance(exc, a.APITimeoutError):
            return AiError("timeout", TIMEOUT_MESSAGE)
        if isinstance(exc, a.APIConnectionError):
            return AiError("network", message("network", LABEL))
        if isinstance(exc, a.APIStatusError):
            return self._status_error(exc)
        return AiError("server", message("server", LABEL))

    def _status_error(self, exc: Any) -> AiError:
        body = getattr(exc, "body", None)
        log.warning("%s answered HTTP %d", LABEL, exc.status_code)
        if exc.status_code in CREDIT_STATUSES and _mentions_credit(body):
            return AiError("credit", message("credit", LABEL))
        # Claude reports a bad key as 401, so a 400 is never "auth" even when its text mentions a key.
        key_sent = exc.status_code != 400
        return error_for(LABEL, exc.status_code, body, key_sent, TIMEOUT_SECONDS, secrets=(self._api_key,))


def _mentions_credit(body: Any) -> bool:
    error = body.get("error") if isinstance(body, dict) else None
    text = error.get("message") if isinstance(error, dict) else None
    return isinstance(text, str) and CREDIT_TEXT in text


def result_from(response: Any) -> AiResult:
    """Parse a messages.create response; raises AiError carrying the token counts on failure."""
    tokens = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        raise AiError("refusal", REFUSAL_MESSAGE, **tokens)
    if response.stop_reason == "max_tokens":
        raise AiError("bad_response", message("cut_off", LABEL), cut_off=True, **tokens)
    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        data = json.loads(text) if text is not None else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        log.warning("Claude returned no readable JSON object (stop reason %s)", response.stop_reason)
        raise AiError("bad_response", message("bad_response", LABEL), **tokens)
    return AiResult(data, **tokens)
