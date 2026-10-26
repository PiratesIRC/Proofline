import json
import logging

import httpx2
import pytest

from proofline.ai_gemini import GeminiBackend
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
    "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3},
}
REQUEST = AiRequest(job="rephrase", system="Fix the text.", text="hello there", schema=OK_SCHEMA, max_tokens=50)
SECRET_TEXT = "SECRET TEXT"
SECRET_KEY = "g-key-SECRET"


def recorder(seen, body=OK_BODY, status=200):
    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json=body)

    return handler


def backend_for(handler, key="g-key"):
    spec = provider("gemini")
    return GeminiBackend(spec, key, transport=httpx2.MockTransport(handler))


def sent_body(request):
    return json.loads(request.content)


def test_gemini_key_in_header_not_url():
    seen = []
    backend_for(recorder(seen)).send(REQUEST, "gemini-2.5-flash-lite")
    request = seen[0]
    assert request.headers["x-goog-api-key"] == "g-key"
    assert "g-key" not in str(request.url)
    assert "key=" not in request.url.query.decode()


def test_gemini_request_shape():
    seen = []
    result = backend_for(recorder(seen)).send(REQUEST, "gemini-2.5-flash-lite")
    request = seen[0]
    body = sent_body(request)
    assert str(request.url) == ("https://generativelanguage.googleapis.com/v1beta/models/"
                                "gemini-2.5-flash-lite:generateContent")
    assert result.data == {"ok": True}
    assert body["systemInstruction"] == {"parts": [{"text": "Fix the text."}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello there"}]}]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["maxOutputTokens"] == 50


def test_gemini_model_name_is_url_encoded():
    seen = []
    backend_for(recorder(seen)).send(REQUEST, "a/b")
    assert "a%2Fb:generateContent" in seen[0].url.raw_path.decode()


@pytest.mark.parametrize("model,thinking", [
    ("gemini-2.5-flash-lite", None),
    ("gemini-3.5-flash-lite", {"thinkingLevel": "minimal"}),
    ("gemini-2.5-pro", {"thinkingLevel": "low"}),
])
def test_gemini_thinking_per_model(model, thinking):
    seen = []
    backend_for(recorder(seen)).send(REQUEST, model)
    assert sent_body(seen[0])["generationConfig"].get("thinkingConfig") == thinking


def test_gemini_schema_sent_without_additional_properties():
    seen = []
    backend_for(recorder(seen)).send(REQUEST, "gemini-2.5-flash-lite")
    schema = sent_body(seen[0])["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in json.dumps(schema)
    assert schema["properties"] == {"ok": {"type": "boolean"}}


def test_gemini_tokens_include_thoughts():
    body = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 7},
    }
    result = backend_for(recorder([], body=body)).send(REQUEST, "gemini-2.5-pro")
    assert (result.input_tokens, result.output_tokens) == (10, 12)


def test_gemini_text_parts_are_joined():
    body = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": '}, {"text": "true}"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }
    assert backend_for(recorder([], body=body)).send(REQUEST, "m").data == {"ok": True}


@pytest.mark.parametrize("answer", [
    {"promptFeedback": {"blockReason": "SAFETY"}},
    {"candidates": [{"finishReason": "PROHIBITED_CONTENT"}]},
])
def test_gemini_blocked_is_refusal(answer):
    with pytest.raises(AiError) as caught:
        backend_for(recorder([], body=answer)).send(REQUEST, "gemini-2.5-flash-lite")
    assert caught.value.kind == "refusal"
    assert caught.value.message == "Gemini declined this request."


def test_gemini_max_tokens_is_cut_off():
    body = {"candidates": [{"content": {"parts": [{"text": "{"}]}, "finishReason": "MAX_TOKENS"}]}
    with pytest.raises(AiError) as caught:
        backend_for(recorder([], body=body)).send(REQUEST, "m")
    assert caught.value.kind == "bad_response"
    assert caught.value.message == "Gemini's answer was cut off."


def test_gemini_bad_key_is_auth_error():
    handler = recorder([], body={"error": {"message": "API key not valid"}}, status=400)
    with pytest.raises(AiError) as caught:
        backend_for(handler).send(REQUEST, "m")
    assert caught.value.kind == "auth"


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
    backend_for(recorder([]), key=SECRET_KEY).send(request, "m")
    with pytest.raises(AiError) as caught:
        backend_for(recorder([], body={"error": {"message": "bad"}}, status=401),
                    key=SECRET_KEY).send(request, "m")
    assert caplog.records
    assert not any(
        SECRET_TEXT in record.getMessage() or SECRET_KEY in record.getMessage() for record in caplog.records
    )
    assert SECRET_KEY not in caught.value.message
    assert SECRET_TEXT not in caught.value.message


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
    GeminiBackend(provider("gemini"), "g-key", transport=transport).send(REQUEST, "gemini-2.5-flash-lite")
    assert transport.closed


def test_schema_nested_objects_and_arrays_have_no_additional_properties():
    nested = {
        "type": "object",
        "properties": {
            "item": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "additionalProperties": False,
                },
            },
        },
        "required": ["item", "items"],
        "additionalProperties": False,
    }
    request = AiRequest(job="rephrase", system="Fix.", text="x", schema=nested, max_tokens=50)
    body = {
        "candidates": [{"content": {"parts": [{"text": '{"item": {"name": "a"}, "items": []}'}]},
                        "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }
    seen = []
    backend_for(recorder(seen, body=body)).send(request, "gemini-2.5-flash-lite")
    sent = sent_body(seen[0])["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in json.dumps(sent)
    assert sent["properties"]["items"]["items"]["properties"] == {"id": {"type": "integer"}}
    assert nested["additionalProperties"] is False


def test_gemini_400_naming_an_api_key_is_auth_only_for_gemini():
    handler = recorder([], body={"error": {"message": "Invalid API key"}}, status=400)
    with pytest.raises(AiError) as caught:
        backend_for(handler).send(REQUEST, "m")
    assert caught.value.kind == "auth"


def test_gemini_cut_off_answer_carries_the_cut_off_marker():
    handler = recorder([], body={"candidates": [{"content": {"parts": [{"text": "{"}]}, "finishReason": "MAX_TOKENS"}]})
    with pytest.raises(AiError) as caught:
        backend_for(handler).send(REQUEST, "m")
    assert caught.value.cut_off is True
