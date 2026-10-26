"""Real requests to each AI provider. Each test runs only when its environment variables are set.

Cloud providers: PROOFLINE_TEST_<ID>_KEY (PROOFLINE_TEST_ANTHROPIC_KEY for Claude). The model is the
provider's default unless PROOFLINE_TEST_<ID>_MODEL is set. Ollama: PROOFLINE_TEST_OLLAMA_URL and
PROOFLINE_TEST_OLLAMA_MODEL. Other server: PROOFLINE_TEST_OTHER_URL, PROOFLINE_TEST_OTHER_MODEL and
optionally PROOFLINE_TEST_OTHER_KEY. Without the variables every test is skipped, so no real API is called.
"""

import os

import pytest

from proofline.ai_backends import make_backend
from proofline.ai_prices import default_model
from proofline.ai_providers import provider
from proofline.ai_setup import key_test_request

CLOUD_IDS = ("anthropic", "openai", "gemini", "grok", "mistral", "deepseek", "groq", "openrouter")


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _key_var(pid: str) -> str:
    return f"PROOFLINE_TEST_{pid.upper()}_KEY"


def _model_for(pid: str) -> str:
    return _env(f"PROOFLINE_TEST_{pid.upper()}_MODEL") or default_model(pid)


def _cloud_param(pid: str):
    """One parameter for a cloud provider, skipped unless its key variable and a model are available."""
    ready = bool(_env(_key_var(pid)) and _model_for(pid))
    reason = f"set {_key_var(pid)} to run (and PROOFLINE_TEST_{pid.upper()}_MODEL, if the provider has no default)"
    return pytest.param(pid, marks=pytest.mark.skipif(not ready, reason=reason))


def _assert_answers(pid: str, key: str | None, address: str, model: str) -> None:
    result = make_backend(provider(pid), key, address).send(key_test_request(), model)
    assert result.data["ok"] is True
    assert result.input_tokens > 0


@pytest.mark.parametrize("pid", [_cloud_param(pid) for pid in CLOUD_IDS])
def test_cloud_provider_answers_with_the_schema(pid):
    _assert_answers(pid, _env(_key_var(pid)), "", _model_for(pid))


_OLLAMA_READY = bool(_env("PROOFLINE_TEST_OLLAMA_URL") and _env("PROOFLINE_TEST_OLLAMA_MODEL"))


@pytest.mark.skipif(not _OLLAMA_READY,
                    reason="set PROOFLINE_TEST_OLLAMA_URL and PROOFLINE_TEST_OLLAMA_MODEL to run")
def test_ollama_answers_with_the_schema():
    _assert_answers("ollama", None, _env("PROOFLINE_TEST_OLLAMA_URL"), _env("PROOFLINE_TEST_OLLAMA_MODEL"))


_OTHER_READY = bool(_env("PROOFLINE_TEST_OTHER_URL") and _env("PROOFLINE_TEST_OTHER_MODEL"))


@pytest.mark.skipif(not _OTHER_READY,
                    reason="set PROOFLINE_TEST_OTHER_URL and PROOFLINE_TEST_OTHER_MODEL to run")
def test_other_server_answers_with_the_schema():
    _assert_answers("other", _env("PROOFLINE_TEST_OTHER_KEY") or None,
                    _env("PROOFLINE_TEST_OTHER_URL"), _env("PROOFLINE_TEST_OTHER_MODEL"))
