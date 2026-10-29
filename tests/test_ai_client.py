import logging
import threading
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from proofline import ai_client, ai_http
from proofline.ai_client import (
    AiError,
    AiRequest,
    AnthropicBackend,
    result_from,
)
from proofline.logging_setup import set_debug_mode, setup_logging

REQUEST = AiRequest("test", "Answer.", "Reply with ok true.", {"type": "object"}, 50)
SECRET_KEY = "sk-ant-secret-key-12345"
SECRET_TEXT = "Confidential sentence about the merger."
OK_MESSAGE = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-haiku-5-5",
    "content": [{"type": "text", "text": '{"ok": true}'}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 40, "output_tokens": 6},
}


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


def test_messages_match_the_other_providers():
    assert ai_client.AUTH_MESSAGE == "Claude did not accept the API key."
    assert ai_client.TIMEOUT_MESSAGE == "Claude took longer than 20 seconds. Try again."
    assert ai_client.REFUSAL_MESSAGE == "Claude declined this request."


def with_transport(monkeypatch, handler):
    """Route the Claude backend's HTTP client through a mock transport, the way make_client would."""
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(ai_client, "make_client", lambda timeout: ai_http.make_client(timeout, transport))


def answer(status=200, body=OK_MESSAGE):
    def handler(request):
        return httpx.Response(status, json=body)

    return handler


def error_body(message, kind="invalid_request_error"):
    return {"type": "error", "error": {"type": kind, "message": message}}


@pytest.mark.parametrize("status", [400, 402])
def test_low_credit_is_credit_kind(monkeypatch, status):
    with_transport(monkeypatch, answer(status, error_body("Your credit balance is too low.")))
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == "credit"
    assert str(caught.value) == "Claude says the account is out of credit."


def test_bad_key_message_names_claude(monkeypatch):
    with_transport(monkeypatch, answer(401, error_body("invalid x-api-key", "authentication_error")))
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == "auth"
    assert str(caught.value) == "Claude did not accept the API key."


def test_rejected_message_carries_the_api_explanation(monkeypatch):
    with_transport(monkeypatch, answer(404, error_body("model: not_found", "not_found_error")))
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == "rejected"
    assert str(caught.value) == "Claude refused the request: model: not_found"


def test_server_and_rate_limit_messages_name_claude(monkeypatch):
    with_transport(monkeypatch, answer(429, error_body("slow down", "rate_limit_error")))
    with pytest.raises(AiError) as limited:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert str(limited.value) == "Claude is limiting requests. Try again in a minute."
    with_transport(monkeypatch, answer(500, error_body("oops", "api_error")))
    with pytest.raises(AiError) as broken:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert broken.value.kind == "server"
    assert str(broken.value) == "Claude had a problem. Try again."


def test_connection_failure_is_network_kind(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")

    with_transport(monkeypatch, handler)
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == "network"
    assert str(caught.value) == "Could not reach Claude."


def test_client_is_closed_after_every_send(monkeypatch):
    closed = []
    real_close = httpx.Client.close

    def record_close(self):
        closed.append(True)
        real_close(self)

    monkeypatch.setattr(httpx.Client, "close", record_close)
    with_transport(monkeypatch, answer())
    AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    with_transport(monkeypatch, answer(500, error_body("oops", "api_error")))
    with pytest.raises(AiError):
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert len(closed) == 2


def test_a_slow_claude_answer_is_a_timeout_at_the_total_limit(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(ai_client, "TIMEOUT_SECONDS", 0.05)

    def handler(request):
        release.wait(5)  # no answer within the limit
        return httpx.Response(200, json=OK_MESSAGE)

    with_transport(monkeypatch, handler)
    try:
        with pytest.raises(AiError) as caught:
            AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    finally:
        release.set()
    assert caught.value.kind == "timeout"
    assert caught.value.__context__ is None


def test_base_url_is_fixed_even_with_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://evil.example")
    backend = AnthropicBackend("sk-ant-test")
    assert backend._client.base_url.host == "api.anthropic.com"


def test_proxy_environment_is_ignored(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:1")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=OK_MESSAGE)

    with_transport(monkeypatch, handler)
    backend = AnthropicBackend(SECRET_KEY)
    assert backend._http.trust_env is False
    assert backend.send(REQUEST, "claude-haiku-5-5").data == {"ok": True}
    assert len(seen) == 1 and seen[0].url.host == "api.anthropic.com"


def test_bad_request_mentioning_the_key_is_rejected_not_auth(monkeypatch):
    with_transport(monkeypatch, answer(400, error_body("Invalid API key format in request.")))
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.kind == "rejected"
    assert str(caught.value) == "Claude refused the request: Invalid API key format in request."


def test_raised_error_keeps_no_sdk_exception(monkeypatch):
    with_transport(monkeypatch, answer(401, error_body("invalid x-api-key", "authentication_error")))
    with pytest.raises(AiError) as caught:
        AnthropicBackend(SECRET_KEY).send(REQUEST, "claude-haiku-5-5")
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


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


@pytest.fixture
def app_logging(tmp_path):
    """The app's real logging setup with debug mode on, as a user with debug logging would have."""
    handlers = setup_logging(tmp_path)
    set_debug_mode(True)
    yield
    set_debug_mode(False)
    root = logging.getLogger()
    for handler in handlers:
        root.removeHandler(handler)
        handler.close()


def test_claude_backend_logs_no_key_or_text(app_logging, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    for name in ("httpx2", "httpcore2"):  # the anthropic logger stays at the app's WARNING level
        caplog.set_level(logging.DEBUG, logger=name)
    request = AiRequest("rephrase", "Fix.", SECRET_TEXT, {"type": "object"}, 50)
    with_transport(monkeypatch, answer())
    AnthropicBackend(SECRET_KEY).send(request, "claude-haiku-5-5")
    with_transport(monkeypatch, answer(401, error_body("invalid x-api-key", "authentication_error")))
    with pytest.raises(AiError):
        AnthropicBackend(SECRET_KEY).send(request, "claude-haiku-5-5")
    assert caplog.records
    assert not any(
        SECRET_TEXT in record.getMessage() or SECRET_KEY in record.getMessage() for record in caplog.records
    )


def test_claude_cut_off_answer_carries_the_cut_off_marker():
    with pytest.raises(AiError) as caught:
        ai_client.result_from(response(stop="max_tokens"))
    assert caught.value.kind == "bad_response" and caught.value.cut_off is True
