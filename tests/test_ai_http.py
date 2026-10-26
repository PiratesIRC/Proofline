import logging

import httpx2
import pytest

from proofline.ai_http import error_for, get_json, make_client, message, post_json
from proofline.ai_types import AiError
from proofline.logging_setup import set_debug_mode, setup_logging

URL = "https://api.example/v1/chat"
SECRET_KEY = "sk-SECRET-KEY-123"
SECRET_TEXT = "secret typed text"


def answer(status, body=None, *, text=None):
    def handler(request):
        if text is not None:
            return httpx2.Response(status, content=text.encode("utf-8"))
        return httpx2.Response(status, json=body if body is not None else {})

    return handler


def send(handler, *, key_sent=True, **kwargs):
    client = make_client(20, httpx2.MockTransport(handler))
    headers = {"Authorization": f"Bearer {SECRET_KEY}"}
    return post_json(client, URL, headers, {"text": SECRET_TEXT}, "Groq", key_sent, **kwargs)


def raising(exc):
    def handler(request):
        raise exc

    return handler


def test_success_returns_the_json_object():
    assert send(answer(200, {"ok": True})) == {"ok": True}


def test_get_returns_the_json_object():
    client = make_client(20, httpx2.MockTransport(answer(200, {"models": []})))
    assert get_json(client, URL, {}, "Groq", True) == {"models": []}


@pytest.mark.parametrize("text", ["[1, 2]", "not json", '"just a string"'])
def test_non_object_success_body_is_bad_response(text):
    with pytest.raises(AiError) as caught:
        send(answer(200, text=text))
    assert caught.value.kind == "bad_response"
    assert caught.value.message == "Groq's answer could not be read."


def test_timeout_is_reported_with_the_limit():
    with pytest.raises(AiError) as caught:
        send(raising(httpx2.ReadTimeout("slow")))
    assert caught.value.kind == "timeout"
    assert "20 seconds" in caught.value.message


def test_connection_error_is_network():
    with pytest.raises(AiError) as caught:
        send(raising(httpx2.ConnectError("refused")))
    assert (caught.value.kind, caught.value.message) == ("network", "Could not reach Groq.")


def test_network_message_replaces_the_generic_text():
    with pytest.raises(AiError) as caught:
        send(raising(httpx2.ConnectError("refused")), network_message="Ollama is not running here.")
    assert (caught.value.kind, caught.value.message) == ("network", "Ollama is not running here.")


def test_overrides_are_raised_before_error_for():
    override = AiError("rejected", "That model is not installed.")
    with pytest.raises(AiError) as caught:
        send(answer(404, {"error": "missing"}), overrides={404: override})
    assert caught.value is override


def test_redirect_is_an_error_and_not_followed():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx2.Response(307, headers={"location": "https://other.example/x"})

    with pytest.raises(AiError) as info:
        post_json(make_client(5, httpx2.MockTransport(handler)), URL, {}, {}, "X", True)
    assert info.value.kind == "rejected" and seen == ["api.example"]


def test_client_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:1")
    assert make_client(5).trust_env is False


@pytest.mark.parametrize(
    ("status", "body", "key_sent", "kind"),
    [
        (401, {}, True, "auth"),
        (403, {}, True, "auth"),
        (401, {}, False, "rejected"),
        (400, {"error": {"message": "API key not valid"}}, True, "auth"),
        (400, {"error": {"message": "API_KEY missing"}}, True, "auth"),
        (400, {"error": {"message": "API key not valid"}}, False, "rejected"),
        (402, {}, True, "credit"),
        (429, {"error": {"code": "credit_balance_exhausted"}}, True, "credit"),
        (429, {}, True, "rate_limit"),
        (503, {}, True, "server"),
        (418, {"error": {"message": "teapot"}}, True, "rejected"),
    ],
)
def test_error_for(status, body, key_sent, kind):
    assert error_for("Groq", status, body, key_sent, key_hint_400=True).kind == kind


def test_rejected_message_carries_the_provider_text():
    error = error_for("Groq", 400, {"error": {"message": "Bad field"}}, False)
    assert error.message == "Groq refused the request: Bad field"


def test_rejected_message_accepts_a_string_error():
    assert error_for("Groq", 400, {"error": "boom"}, False).message == "Groq refused the request: boom"


def test_rejected_message_falls_back_to_the_status():
    assert error_for("Groq", 418, "not an object", True).message == "Groq refused the request (HTTP 418)."


def test_message_templates():
    assert message("timeout", "Groq", seconds=20) == "Groq took longer than 20 seconds. Try again."
    assert message("rejected", "X", status=307) == "X refused the request (HTTP 307)."
    assert message("credit", "Groq") == "Groq says the account is out of credit."


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


def test_errors_never_contain_url_key_or_text(app_logging, caplog):
    # httpx2 logs "POST <url>" at INFO; the app's setup keeps it at WARNING (NOISY_LOGGERS).
    caplog.set_level(logging.DEBUG)
    assert send(answer(200, {"ok": True})) == {"ok": True}
    failures = [
        answer(500),
        answer(401),
        answer(400, {"error": {"message": "bad"}}),
        raising(httpx2.ReadTimeout("x")),
    ]
    for handler in failures:
        with pytest.raises(AiError) as caught:
            send(handler)
        assert "api.example" not in caught.value.message
        assert SECRET_KEY not in caught.value.message
        assert SECRET_TEXT not in caught.value.message
    assert "api.example" not in caplog.text
    assert SECRET_KEY not in caplog.text
    assert SECRET_TEXT not in caplog.text


def test_provider_text_echoing_the_key_is_dropped():
    with pytest.raises(AiError) as caught:
        send(answer(422, {"error": {"message": f"Invalid key {SECRET_KEY} in request"}}))
    assert caught.value.kind == "rejected"
    assert caught.value.message == "Groq refused the request (HTTP 422)."


def test_bare_key_in_provider_text_is_dropped():
    error = error_for("Groq", 400, {"error": {"message": "unknown key sk-bare-1"}}, False, secrets=("sk-bare-1",))
    assert error.message == "Groq refused the request (HTTP 400)."


def test_long_provider_text_is_capped():
    error = error_for("Groq", 400, {"error": {"message": "x" * 500}}, False)
    assert error.message == "Groq refused the request: " + "x" * 200 + "..."
    assert len(error.message) < 260


def test_key_echo_is_still_classified_as_auth():
    error = error_for(
        "Groq",
        401,
        {"error": {"message": "Incorrect API key provided: sk-test-KEY"}},
        True,
        secrets=("Bearer sk-test-KEY",),
    )
    assert error.kind == "auth"
    assert "sk-test-KEY" not in error.message


def test_short_secrets_are_not_scanned_for():
    error = error_for("Groq", 400, {"error": {"message": "error 0 in true field"}}, False, secrets=("0", "true"))
    assert error.message == "Groq refused the request: error 0 in true field"


def test_non_credential_header_values_are_kept():
    def handler(request):
        return httpx2.Response(400, json={"error": {"message": "Use application/json bodies"}})

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {SECRET_KEY}"}
    client = make_client(20, httpx2.MockTransport(handler))
    with pytest.raises(AiError) as caught:
        post_json(client, URL, headers, {}, "Groq", True)
    assert caught.value.kind == "rejected"
    assert caught.value.message == "Groq refused the request: Use application/json bodies"


@pytest.mark.parametrize("hint", ["Invalid API key", "API_KEY is missing"])
def test_openai_format_400_mentioning_a_key_is_rejected_not_auth(hint):
    """Only Gemini reports a bad key as HTTP 400, so other providers' 400 text is never read as auth."""
    error = error_for("Groq", 400, {"error": {"message": hint}}, True)
    assert error.kind == "rejected"


def test_gemini_style_400_mentioning_a_key_is_auth():
    error = error_for("Gemini", 400, {"error": {"message": "API key not valid"}}, True, key_hint_400=True)
    assert error.kind == "auth"


def test_post_json_passes_the_400_key_rule_through():
    handler = lambda request: httpx2.Response(400, json={"error": {"message": "API key not valid"}})
    with pytest.raises(AiError) as caught:
        send(handler, key_hint_400=True)
    assert caught.value.kind == "auth"
    with pytest.raises(AiError) as caught:
        send(handler)
    assert caught.value.kind == "rejected"
