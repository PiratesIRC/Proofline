import httpx2
import pytest

from proofline.ai_model_list import ModelChoice, fetch_models
from proofline.ai_prices import ModelPrice
from proofline.ai_providers import provider
from proofline.ai_types import AiError

OPENROUTER_BODY = {
    "data": [
        {
            "id": "vendor/zeta",
            "name": "Zeta",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "supported_parameters": ["max_tokens", "structured_outputs"],
        },
        {
            "id": "vendor/alpha",
            "name": "",
            "pricing": {"prompt": "0.0000002", "completion": "0.000001"},
            "supported_parameters": ["structured_outputs"],
        },
        {
            "id": "vendor/plain",
            "name": "Plain",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000001"},
            "supported_parameters": ["max_tokens"],
        },
        {
            "id": "vendor/unpriced",
            "name": "Unpriced",
            "pricing": {"prompt": "free", "completion": "0.0000001"},
            "supported_parameters": ["structured_outputs"],
        },
        {
            "id": "vendor/no-pricing",
            "name": "No pricing",
            "supported_parameters": ["structured_outputs"],
        },
    ]
}


def recorder(seen, body, status=200):
    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json=body)

    return handler


def fetch(spec_id, body, *, key=None, base_url="", status=200, seen=None):
    seen = [] if seen is None else seen
    choices = fetch_models(provider(spec_id), base_url, key, transport=httpx2.MockTransport(recorder(seen, body, status)))
    return choices, seen


def test_openrouter_list_filters_structured_outputs_and_converts_prices():
    choices, seen = fetch("openrouter", OPENROUTER_BODY, key="or-key")
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/models"
    assert seen[0].headers["authorization"] == "Bearer or-key"
    assert [choice.model_id for choice in choices] == ["vendor/alpha", "vendor/zeta"]
    alpha, zeta = choices
    assert alpha == ModelChoice(
        "vendor/alpha", "vendor/alpha",
        ModelPrice("openrouter", "vendor/alpha", "vendor/alpha", pytest.approx(0.2), pytest.approx(1.0)),
    )
    assert zeta.label == "Zeta"
    assert zeta.price.provider == "openrouter"
    assert zeta.price.input_per_million == pytest.approx(0.1)
    assert zeta.price.output_per_million == pytest.approx(0.4)


def test_openrouter_list_without_key_sends_no_authorization():
    _, seen = fetch("openrouter", {"data": []})
    assert "authorization" not in seen[0].headers


def test_openrouter_key_is_never_in_the_url():
    _, seen = fetch("openrouter", OPENROUTER_BODY, key="or-key")
    assert "or-key" not in str(seen[0].url)


def test_ollama_list():
    choices, seen = fetch("ollama", {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2"}]},
                          base_url="http://localhost:11434/")
    assert str(seen[0].url) == "http://localhost:11434/api/tags"
    assert "authorization" not in seen[0].headers
    assert [choice.model_id for choice in choices] == ["llama3.2", "qwen2.5:7b"]
    assert [choice.label for choice in choices] == ["llama3.2", "qwen2.5:7b"]
    assert all(choice.price is None for choice in choices)


def test_other_list_sends_key_only_when_given():
    body = {"data": [{"id": "local-b"}, {"id": "Local-a"}]}
    choices, seen = fetch("other", body, key="other-key", base_url="http://localhost:1234/v1/")
    assert str(seen[0].url) == "http://localhost:1234/v1/models"
    assert seen[0].headers["authorization"] == "Bearer other-key"
    assert "other-key" not in str(seen[0].url)
    assert [choice.label for choice in choices] == ["Local-a", "local-b"]
    assert all(choice.price is None for choice in choices)

    _, seen = fetch("other", body, base_url="http://localhost:1234/v1")
    assert "authorization" not in seen[0].headers


def test_ollama_never_sends_a_key():
    _, seen = fetch("ollama", {"models": []}, key="sk-should-not-go", base_url="http://localhost:11434")
    assert "authorization" not in seen[0].headers
    assert "sk-should-not-go" not in str(seen[0].url)


def test_blank_key_is_no_key_and_401_is_rejected():
    _, seen = fetch("other", {"data": []}, key="", base_url="http://localhost:1234/v1")
    assert "authorization" not in seen[0].headers
    with pytest.raises(AiError) as caught:
        fetch("other", {"error": "no"}, key="", base_url="http://localhost:1234/v1", status=401)
    assert caught.value.kind == "rejected"


def test_negative_and_nan_prices_are_skipped():
    body = {
        "data": [
            {"id": "vendor/negative", "name": "Negative", "supported_parameters": ["structured_outputs"],
             "pricing": {"prompt": "-0.0000001", "completion": "0.0000001"}},
            {"id": "vendor/nan", "name": "Nan", "supported_parameters": ["structured_outputs"],
             "pricing": {"prompt": "nan", "completion": "0.0000001"}},
            {"id": "vendor/kept", "name": "Kept", "supported_parameters": ["structured_outputs"],
             "pricing": {"prompt": "0.0000001", "completion": "0.0000001"}},
        ]
    }
    choices, _ = fetch("openrouter", body, key="or-key")
    assert [choice.model_id for choice in choices] == ["vendor/kept"]


def test_list_errors_use_provider_messages():
    with pytest.raises(AiError) as caught:
        fetch("openrouter", {"error": {"message": "bad key"}}, key="or-key", status=401)
    assert caught.value.kind == "auth"
    assert caught.value.message == "OpenRouter did not accept the API key."


def test_malformed_list_raises_bad_response():
    with pytest.raises(AiError) as caught:
        fetch("ollama", {"models": "nope"}, base_url="http://localhost:11434")
    assert caught.value.kind == "bad_response"
    assert caught.value.message == "Ollama's answer could not be read."


def test_unreachable_server_raises_network():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(AiError) as caught:
        fetch_models(provider("other"), "http://localhost:1234/v1", None,
                     transport=httpx2.MockTransport(handler))
    assert caught.value.kind == "network"
    assert caught.value.message == "Could not reach Other server."


def test_client_closed_after_fetch():
    class ClosingTransport(httpx2.MockTransport):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    transport = ClosingTransport(recorder([], {"models": []}))
    fetch_models(provider("ollama"), "http://localhost:11434", None, transport=transport)
    assert transport.closed
