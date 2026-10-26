import json
import logging

import httpx2
import pytest

from proofline.ai_backends import make_backend
from proofline.ai_client import AnthropicBackend
from proofline.ai_gemini import GeminiBackend
from proofline.ai_ollama import OllamaBackend
from proofline.ai_openai_compat import OpenAICompatBackend
from proofline.ai_providers import provider
from proofline.ai_types import AiError, AiRequest
from proofline.logging_setup import set_debug_mode, setup_logging

OK_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
OK_BODY = {
    "message": {"role": "assistant", "content": '{"ok": true}'},
    "done": True,
    "prompt_eval_count": 12,
    "eval_count": 3,
}
REQUEST = AiRequest(job="rephrase", system="Fix the text.", text="hello there", schema=OK_SCHEMA, max_tokens=50)
LOCAL_URL = "http://localhost:11434"
SECRET_TEXT = "SECRET TEXT"
SECRET_KEY = "ollama-key-SECRET"  # Ollama takes no key; this checks that none leaks into a message


def recorder(seen, body=OK_BODY, status=200):
    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json=body)

    return handler


def backend_for(handler, base_url=LOCAL_URL):
    return OllamaBackend(provider("ollama"), base_url, transport=httpx2.MockTransport(handler))


def sent_body(request):
    return json.loads(request.content)


def test_ollama_request_shape():
    seen = []
    result = backend_for(recorder(seen)).send(REQUEST, "llama3.2")
    request = seen[0]
    body = sent_body(request)
    assert str(request.url) == "http://localhost:11434/api/chat"
    assert body["model"] == "llama3.2"
    assert body["stream"] is False
    assert body["format"] == OK_SCHEMA
    assert body["think"] is False
    assert body["options"] == {"num_ctx": 8192, "num_predict": 50}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == "hello there"
    assert "authorization" not in request.headers
    assert result.data == {"ok": True}
    assert (result.input_tokens, result.output_tokens) == (12, 3)


def test_ollama_unknown_model_message():
    handler = recorder([], body={"error": "model not found"}, status=404)
    with pytest.raises(AiError) as caught:
        backend_for(handler).send(REQUEST, "llama9")
    assert caught.value.kind == "rejected"
    assert "llama9" in caught.value.message
    assert "Refresh" in caught.value.message


def test_ollama_not_running_message():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(AiError) as caught:
        backend_for(handler).send(REQUEST, "llama3.2")
    assert caught.value.kind == "network"
    assert caught.value.message == "Could not reach Ollama at http://localhost:11434. Is it running?"


def test_ollama_address_with_credentials_is_redacted_in_message():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(AiError) as caught:
        backend_for(handler, base_url="http://user:pw-SECRET@lan-box:11434").send(REQUEST, "llama3.2")
    assert "pw-SECRET" not in caught.value.message
    assert "***@lan-box:11434" in caught.value.message


def test_ollama_timeout_follows_local_provider():
    assert backend_for(recorder([])).timeout == 120.0


def test_ollama_trailing_slash_is_dropped():
    seen = []
    backend_for(recorder(seen), base_url="http://localhost:11434/").send(REQUEST, "m")
    assert str(seen[0].url) == "http://localhost:11434/api/chat"


def test_make_backend_picks_by_protocol():
    assert isinstance(make_backend(provider("anthropic"), "k", ""), AnthropicBackend)
    assert isinstance(make_backend(provider("gemini"), "k", ""), GeminiBackend)
    assert isinstance(make_backend(provider("ollama"), None, LOCAL_URL), OllamaBackend)
    openai = make_backend(provider("openai"), "k", "")
    assert isinstance(openai, OpenAICompatBackend)
    assert openai.base_url == "https://api.openai.com/v1"
    other = make_backend(provider("other"), None, "http://localhost:1234/v1")
    assert isinstance(other, OpenAICompatBackend)
    assert other.base_url == "http://localhost:1234/v1"


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


def test_key_and_text_never_logged(app_logging, caplog):
    caplog.set_level(logging.DEBUG)
    for name in ("httpx2", "httpcore2"):
        caplog.set_level(logging.DEBUG, logger=name)
    request = AiRequest(job="rephrase", system="Fix.", text=SECRET_TEXT, schema=OK_SCHEMA, max_tokens=50)
    backend_for(recorder([])).send(request, "m")

    def refuse(_request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(AiError) as caught:
        backend_for(refuse).send(request, "m")
    assert caplog.records
    assert not any(SECRET_TEXT in record.getMessage() for record in caplog.records)
    assert SECRET_TEXT not in caught.value.message
    assert SECRET_KEY not in caught.value.message


class ClosingTransport(httpx2.MockTransport):
    """A mock transport that records whether the client that used it has closed it."""

    def __init__(self, handler):
        super().__init__(handler)
        self.closed = False

    def close(self):
        self.closed = True
        super().close()


def test_client_closed_after_send():
    transport = ClosingTransport(recorder([]))
    OllamaBackend(provider("ollama"), LOCAL_URL, transport=transport).send(REQUEST, "llama3.2")
    assert transport.closed
