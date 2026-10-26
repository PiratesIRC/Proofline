from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from proofline.ai_client import (
    AiError,
    AiRequest,
    AnthropicBackend,
    rejected_message,
    result_from,
)

REQUEST = AiRequest("test", "Answer.", "Reply with ok true.", {"type": "object"}, 50)


def response(text='{"ok": true}', stop="end_turn", block_type="text"):
    return SimpleNamespace(
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=40, output_tokens=6),
        content=[SimpleNamespace(type=block_type, text=text)],
    )


def test_result_parses_the_json_and_token_counts():
    result = result_from(response())
    assert result.data == {"ok": True}
    assert (result.input_tokens, result.output_tokens) == (40, 6)


@pytest.mark.parametrize(
    ("given", "kind"),
    [
        (response(stop="refusal"), "refusal"),
        (response(stop="max_tokens"), "bad_response"),
        (response(text="not json"), "bad_response"),
        (response(text="[1, 2]"), "bad_response"),
        (response(block_type="thinking"), "bad_response"),
    ],
)
def test_unusable_answers_raise_with_token_counts(given, kind):
    with pytest.raises(AiError) as caught:
        result_from(given)
    assert caught.value.kind == kind
    assert (caught.value.input_tokens, caught.value.output_tokens) == (40, 6)


def test_rejected_message_uses_the_api_explanation():
    body = {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low."}}
    assert rejected_message(400, body) == "The Claude API refused the request: Your credit balance is too low."
    assert rejected_message(404, None) == "The Claude API refused the request (HTTP 404)."


def status_error(cls, status, body=None):
    http_response = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls("error", response=http_response, body=body)


class RaisingMessages:
    def __init__(self, exc):
        self.exc = exc

    def create(self, **kwargs):
        raise self.exc


@pytest.mark.parametrize(
    ("make_error", "kind"),
    [
        (lambda: status_error(anthropic.AuthenticationError, 401), "auth"),
        (lambda: status_error(anthropic.PermissionDeniedError, 403), "auth"),
        (lambda: status_error(anthropic.RateLimitError, 429), "rate_limit"),
        (lambda: status_error(anthropic.BadRequestError, 400), "rejected"),
        (lambda: status_error(anthropic.InternalServerError, 500), "server"),
        (lambda: anthropic.APITimeoutError(request=httpx.Request("POST", "https://x")), "timeout"),
        (lambda: anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")), "network"),
    ],
)
def test_sdk_errors_map_to_kinds(make_error, kind):
    backend = AnthropicBackend("sk-ant-test")
    backend._client = SimpleNamespace(messages=RaisingMessages(make_error()))
    with pytest.raises(AiError) as caught:
        backend.send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == kind


def test_backend_sends_no_retries_and_a_20_second_timeout():
    backend = AnthropicBackend("sk-ant-test")
    assert backend._client.max_retries == 0
    assert backend._client.timeout == 20.0


def test_backend_sends_the_schema_and_low_effort():
    sent = {}

    class Recording:
        def create(self, **kwargs):
            sent.update(kwargs)
            return response()

    backend = AnthropicBackend("sk-ant-test")
    backend._client = SimpleNamespace(messages=Recording())
    backend.send(REQUEST, "claude-haiku-5-5")
    assert sent["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert sent["messages"] == [{"role": "user", "content": "Reply with ok true."}]
    assert sent["max_tokens"] == 50 and sent["system"] == "Answer."
