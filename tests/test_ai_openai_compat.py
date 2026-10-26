import json
import logging

import httpx2
import pytest

from proofline.ai_openai_compat import OpenAICompatBackend, forget_object_mode
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
    "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
}
REQUEST = AiRequest(job="rephrase", system="Fix the text.", text="hello there", schema=OK_SCHEMA, max_tokens=50)
LOCAL_URL = "http://localhost:1234/v1"
SECRET_TEXT = "SECRET TEXT"
SECRET_KEY = "sk-test-KEY"


@pytest.fixture(autouse=True)
def fresh_object_mode():
    forget_object_mode()
    yield
    forget_object_mode()


def recorder(seen, body=OK_BODY, status=200):
    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json=body)

    return handler


def raw_recorder(body):
    """Answers with body serialised by json.dumps, so NaN and Infinity reach the client as bare literals."""
    def handler(request):
        return httpx2.Response(200, content=json.dumps(body).encode(), headers={"content-type": "application/json"})

    return handler


def backend_for(pid, handler, key="k", base_url=None):
    spec = provider(pid)
    return OpenAICompatBackend(spec, key, base_url or spec.base_url, transport=httpx2.MockTransport(handler))


@pytest.mark.parametrize("pid,url,token_field,extra", [
    ("openai", "https://api.openai.com/v1/chat/completions", "max_completion_tokens", {"reasoning_effort": "low"}),
    ("grok", "https://api.x.ai/v1/chat/completions", "max_completion_tokens", {"reasoning_effort": "low"}),
    ("mistral", "https://api.mistral.ai/v1/chat/completions", "max_tokens", {}),
    ("groq", "https://api.groq.com/openai/v1/chat/completions", "max_completion_tokens", {"reasoning_effort": "low"}),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "max_tokens",
     {"provider": {"require_parameters": True, "data_collection": "deny"}})])
def test_request_shape(pid, url, token_field, extra):
    seen = []
    backend_for(pid, recorder(seen)).send(REQUEST, "model-x")
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == url
    assert request.headers["authorization"] == "Bearer k"
    assert body["model"] == "model-x"
    assert body[token_field] == 50
    for name, value in extra.items():
        assert body[name] == value
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "rephrase"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == OK_SCHEMA
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == "hello there"


def test_openrouter_app_headers():
    seen = []
    backend_for("openrouter", recorder(seen)).send(REQUEST, "m")
    assert seen[0].headers["http-referer"] == "https://github.com/PiratesIRC/Proofline"
    assert seen[0].headers["x-openrouter-title"] == "Proofline"


def test_deepseek_uses_json_object_and_puts_schema_in_prompt():
    seen = []
    backend_for("deepseek", recorder(seen)).send(REQUEST, "deepseek-chat")
    body = json.loads(seen[0].content)
    system = body["messages"][0]["content"]
    assert body["response_format"] == {"type": "json_object"}
    assert "json" in system and '"ok"' in system
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("usage_cost,expected", [(0.0123, 0.0123), (None, None)])
def test_reads_answer_tokens_and_cost(usage_cost, expected):
    body = json.loads(json.dumps(OK_BODY))
    if usage_cost is not None:
        body["usage"]["cost"] = usage_cost
    result = backend_for("openrouter", recorder([], body=body)).send(REQUEST, "m")
    assert result.data == {"ok": True}
    assert (result.input_tokens, result.output_tokens) == (12, 3)
    assert result.cost == expected


def test_other_without_key_sends_no_authorization_header():
    seen = []
    backend_for("other", recorder(seen), key=None, base_url=LOCAL_URL).send(REQUEST, "local")
    assert str(seen[0].url) == LOCAL_URL + "/chat/completions"
    assert "authorization" not in seen[0].headers


def test_other_falls_back_to_object_mode_once_and_remembers():
    seen = []
    refusal = {"error": {"message": "response_format json_schema not supported"}}
    responses = iter([httpx2.Response(400, json=refusal), httpx2.Response(200, json=OK_BODY)])

    def handler(request):
        seen.append(request)
        return next(responses)

    result = backend_for("other", handler, key=None, base_url=LOCAL_URL).send(REQUEST, "local")
    assert result.data == {"ok": True}
    assert len(seen) == 2
    assert json.loads(seen[1].content)["response_format"] == {"type": "json_object"}

    later = []
    backend_for("other", recorder(later), key=None, base_url=LOCAL_URL).send(REQUEST, "local")
    assert json.loads(later[0].content)["response_format"] == {"type": "json_object"}


def test_other_400_without_format_words_is_not_retried():
    seen = []
    handler = recorder(seen, body={"error": {"message": "model not found"}}, status=400)
    with pytest.raises(AiError) as caught:
        backend_for("other", handler, key=None, base_url=LOCAL_URL).send(REQUEST, "local")
    assert caught.value.kind == "rejected"
    assert len(seen) == 1


@pytest.mark.parametrize("body,kind,text", [
    ({"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]},
     "bad_response", "OpenAI's answer was cut off."),
    ({"choices": [{"message": {"content": None, "refusal": "No."}, "finish_reason": "stop"}]},
     "refusal", "OpenAI declined this request."),
])
def test_cut_off_and_refusal(body, kind, text):
    with pytest.raises(AiError) as caught:
        backend_for("openai", recorder([], body=body)).send(REQUEST, "m")
    assert caught.value.kind == kind
    assert caught.value.message == text


def test_timeouts_follow_the_provider():
    openai = backend_for("openai", recorder([]))
    other = backend_for("other", recorder([]), key=None, base_url=LOCAL_URL)
    assert openai.timeout == 20.0
    assert other.timeout == 120.0


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
    spec = provider("openai")
    OpenAICompatBackend(spec, "k", spec.base_url, transport=transport).send(REQUEST, "m")
    assert transport.closed


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
    backend_for("openai", recorder([]), key=SECRET_KEY).send(request, "m")
    with pytest.raises(AiError):
        backend_for("openai", recorder([], body={"error": {"message": "bad"}}, status=401),
                    key=SECRET_KEY).send(request, "m")
    assert caplog.records
    assert not any(
        SECRET_TEXT in record.getMessage() or SECRET_KEY in record.getMessage() for record in caplog.records
    )


def test_malformed_choices_still_report_the_billed_tokens():
    body = {"choices": [], "usage": {"prompt_tokens": 40, "completion_tokens": 7}}
    with pytest.raises(AiError) as caught:
        backend_for("deepseek", recorder([], body=body)).send(REQUEST, "m")
    assert caught.value.kind == "bad_response"
    assert (caught.value.input_tokens, caught.value.output_tokens) == (40, 7)


@pytest.mark.parametrize("reported", [-50, -0.5, float("nan"), float("inf"), "0.02", True])
def test_other_server_cost_is_never_trusted(reported):
    """Only OpenRouter reports a cost Proofline believes; any other server's figure is ignored."""
    body = json.loads(json.dumps(OK_BODY))
    body["usage"]["cost"] = reported
    result = backend_for("other", raw_recorder(body), base_url=LOCAL_URL).send(REQUEST, "m")
    assert result.cost is None


@pytest.mark.parametrize("reported", [-1, float("nan"), float("inf"), "0.02", True])
def test_openrouter_bad_cost_is_ignored(reported):
    body = json.loads(json.dumps(OK_BODY))
    body["usage"]["cost"] = reported
    result = backend_for("openrouter", raw_recorder(body)).send(REQUEST, "m")
    assert result.cost is None


def test_openrouter_zero_cost_is_kept():
    body = json.loads(json.dumps(OK_BODY))
    body["usage"]["cost"] = 0
    result = backend_for("openrouter", recorder([], body=body)).send(REQUEST, "m")
    assert result.cost == 0.0


def test_openai_format_400_naming_an_api_key_is_rejected_not_auth():
    handler = recorder([], body={"error": {"message": "Invalid API key"}}, status=400)
    with pytest.raises(AiError) as caught:
        backend_for("grok", handler).send(REQUEST, "m")
    assert caught.value.kind == "rejected"


def test_cut_off_answer_carries_the_cut_off_marker():
    body = {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}
    with pytest.raises(AiError) as caught:
        backend_for("deepseek", recorder([], body=body)).send(REQUEST, "m")
    assert caught.value.kind == "bad_response" and caught.value.cut_off is True
