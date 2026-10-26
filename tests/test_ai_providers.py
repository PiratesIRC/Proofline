"""The AI provider table, key targets, model-name shape and address checks."""

from __future__ import annotations

import pytest

from proofline.ai_keys import KEY_TARGET
from proofline.ai_providers import (
    PROVIDER_IDS,
    PROVIDERS,
    is_valid_model_name,
    key_target,
    normalize_ai_address,
    provider,
    timeout_for,
)


def test_ten_providers_in_order():
    assert PROVIDER_IDS == ("anthropic", "openai", "gemini", "grok", "mistral", "deepseek", "groq",
                            "openrouter", "ollama", "other")
    # Claude and Ollama passed a live request on 2026-10-26; the rest are untested.
    assert [p.id for p in PROVIDERS if p.tested] == ["anthropic", "ollama"]


def test_cloud_base_urls_are_fixed_https():
    for spec in PROVIDERS:
        assert spec.base_url.startswith("https://") or (spec.id in ("ollama", "other") and spec.base_url == "")


def test_provider_lookup_and_unknown_id():
    assert provider("groq").base_url == "https://api.groq.com/openai/v1"
    with pytest.raises(KeyError):
        provider("nope")


def test_timeouts():
    assert timeout_for(provider("ollama")) == timeout_for(provider("other")) == 120.0
    assert timeout_for(provider("openai")) == 20.0


def test_key_targets():
    assert key_target("anthropic") == "Proofline/anthropic-api-key" == KEY_TARGET
    assert key_target("gemini", "ProoflineTest") == "ProoflineTest/gemini-api-key"


@pytest.mark.parametrize("name,ok", [
    ("gpt-6-luna", True), ("openai/gpt-oss-20b", True), ("qwen2.5:7b", True),
    ("", False), ("a b", False), ("x" * 201, False), ("bad\n", False), (3, False),
])
def test_model_name_shape(name, ok):
    assert is_valid_model_name(name) is ok


@pytest.mark.parametrize("text,expected", [
    (" http://localhost:11434/ ", "http://localhost:11434"),
    ("https://h.example/v1", "https://h.example/v1"),
])
def test_address_normalised(text, expected):
    assert normalize_ai_address(text) == expected


@pytest.mark.parametrize("text", ["ftp://h", "http://u:p@h", "http://h/?q=1", "http://h/#f", "http://", "h:1234"])
def test_address_rejected(text):
    with pytest.raises(ValueError):
        normalize_ai_address(text)


def test_provider_lookup_returns_the_same_object():
    assert provider("deepseek") is provider("deepseek")


@pytest.mark.parametrize("text", [
    "http://localhost:abc", "http://h:99999", "http://h:", "http://h st:1", "http://h:1 2", " http://h :1234",
    "http://h\tx", "http://[::1]:", "http://h:-1",
])
def test_bad_port_or_inner_space_is_rejected(text):
    with pytest.raises(ValueError):
        normalize_ai_address(text)


@pytest.mark.parametrize("text,expected", [
    ("http://localhost:11434", "http://localhost:11434"),
    ("http://[::1]:8080/v1/", "http://[::1]:8080/v1"),
    ("https://ollama.example", "https://ollama.example"),
])
def test_good_port_is_kept(text, expected):
    assert normalize_ai_address(text) == expected
