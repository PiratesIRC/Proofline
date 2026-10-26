"""The Settings AI page wording: provider names, key and address text, privacy lines and usage lines.

Every string here is copied from docs/design/2026-10-26-ai-providers-design.md; the tests pin the
exact wording so a change to the page has to change the design too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proofline import ai_page_text as text
from proofline.ai_prices import ModelPrice, most_expensive
from proofline.ai_providers import PROVIDERS, provider
from proofline.ai_usage import TokenTotals, Totals

MIDDLE_DOT = "\u00b7"
CLOUD_IDS = ("anthropic", "openai", "gemini", "grok", "mistral", "deepseek", "groq", "openrouter")
KEYED_IDS = CLOUD_IDS + ("other",)
CLOUD_TEXT = ("When you ask for an AI suggestion, or press Test, Proofline sends that text (Test sends a "
              "short fixed sentence) to {label} with your key. Nothing is sent otherwise.")
WARNINGS = {
    "gemini": "With a free Gemini key, Google may use your text to improve its products and people may "
              "read it. Paid keys are covered by different terms.",
    "mistral": "Mistral may use API data from free accounts for training. Check the privacy settings in "
               "your Mistral console.",
    "openrouter": "Requests go to the company running the model you pick. Proofline asks OpenRouter to "
                  "skip companies that store or train on your text.",
    "deepseek": "DeepSeek's general privacy policy says it stores data on servers in China.",
}
INSECURE = "This address is not encrypted, so your text can be read on the network."


@pytest.mark.parametrize("spec", PROVIDERS, ids=lambda s: s.id)
def test_provider_item_text(spec):
    expected = f"{spec.label} (untested)" if not spec.tested else spec.label
    assert text.provider_item_text(spec) == expected


def test_provider_item_text_examples():
    assert text.provider_item_text(provider("anthropic")) == "Claude"
    assert text.provider_item_text(provider("gemini")) == "Gemini (untested)"


@pytest.mark.parametrize("pid", KEYED_IDS)
def test_key_title(pid):
    assert text.key_title(provider(pid)) == f"{provider(pid).label} API key"


@pytest.mark.parametrize("pid", CLOUD_IDS)
def test_key_description_cloud(pid):
    spec = provider(pid)
    assert text.key_description(spec) == (
        f"From {spec.key_hint}. Kept in Windows Credential Manager, not in the settings file")


def test_key_description_other_is_optional():
    assert text.key_description(provider("other")) == "Only if your server asks for one"


def test_key_description_gemini_example():
    assert text.key_description(provider("gemini")) == (
        "From aistudio.google.com. Kept in Windows Credential Manager, not in the settings file")


def test_ollama_address_description():
    assert text.ADDRESS_DESCRIPTION["ollama"] == "Ollama's default is http://localhost:11434"
    assert text.ADDRESS_DESCRIPTION["other"] == (
        "The server's OpenAI-compatible address, such as http://localhost:1234/v1")


def test_untested_and_fixed_strings():
    assert text.UNTESTED_TEXT == "(untested)"
    assert text.KEY_REFUSED_INSECURE == "Use https, or turn off the server's key requirement on a trusted network."
    assert text.OTHER_MODEL_TEXT == "Other model..."


def test_untested_note_says_how_to_report_a_problem():
    assert text.UNTESTED_NOTE == (
        "This provider has not been tested with a real account yet. If something does not work, "
        "please report it on GitHub.")


@pytest.mark.parametrize("pid", CLOUD_IDS)
def test_cloud_privacy_text(pid):
    spec = provider(pid)
    expected = CLOUD_TEXT.format(label=spec.label)
    if pid == "openrouter":
        expected += f" Refreshing the model list also contacts {spec.label}."
    assert text.privacy_text(spec, "") == expected


def test_warnings_verbatim():
    for spec in PROVIDERS:
        if spec.id in WARNINGS:
            assert text.warning_text(spec) == WARNINGS[spec.id]
        else:
            assert text.warning_text(spec) == ""


def test_ollama_privacy_localhost_lan_and_cloud():
    spec = provider("ollama")
    assert text.privacy_text(spec, "http://localhost:11434") == "Your text stays on this computer."
    assert text.privacy_text(spec, "http://127.0.0.1:11434") == "Your text stays on this computer."
    assert text.privacy_text(spec, "http://[::1]:11434") == "Your text stays on this computer."
    assert text.privacy_text(spec, "http://ollama.example:11434") == (
        "Your text goes to the computer at this address.")
    assert text.privacy_text(spec, "http://localhost:11434", "gpt-oss:120b-cloud") == (
        "Your text goes to Ollama's servers for this model.")
    assert text.privacy_text(spec, "http://ollama.example:11434", "gpt-oss:120b:cloud") == (
        "Your text goes to Ollama's servers for this model.")


def test_other_privacy():
    assert text.privacy_text(provider("other"), "http://lan.example:1234/v1") == (
        "Your text, and your key if you saved one, go to the server at this address.")


def test_is_ollama_cloud_model():
    assert text.is_ollama_cloud_model("gpt-oss:120b-cloud")
    assert text.is_ollama_cloud_model("qwen3-coder:480b:cloud")
    assert not text.is_ollama_cloud_model("llama3.2:3b")
    assert not text.is_ollama_cloud_model("")


def test_insecure_only_for_remote_http():
    assert text.insecure_text("http://ollama.example:11434") == INSECURE
    assert text.insecure_text("http://lan.example:1234/v1") == INSECURE
    assert text.insecure_text("http://[::1]:11434") == ""
    assert text.insecure_text("http://localhost:1") == ""
    assert text.insecure_text("http://127.0.0.1:11434") == ""
    assert text.insecure_text("https://ollama.example") == ""


@pytest.mark.parametrize("pid", [pid for pid in CLOUD_IDS if pid != "openrouter"])
def test_estimated_price_text_names_most_expensive_model(pid):
    assert text.estimated_price_text(provider(pid)) == f"Cost estimated at {most_expensive(pid).label}'s price"


def test_estimated_price_text_openrouter_uses_dearer_live_price():
    live = (
        ModelPrice("openrouter", "cheap/model", "Cheap Model", 0.10, 0.40),
        ModelPrice("openrouter", "dear/model", "Dear Model", 0.50, 2.00),
    )
    assert text.estimated_price_text(provider("openrouter"), live) == "Cost estimated at Dear Model's price"


def test_estimated_price_text_openrouter_without_live_prices_is_empty():
    assert text.estimated_price_text(provider("openrouter")) == ""
    assert text.estimated_price_text(provider("openrouter"), ()) == ""


def test_estimated_price_text_ollama_and_other_are_empty():
    assert text.estimated_price_text(provider("ollama")) == ""
    assert text.estimated_price_text(provider("other")) == ""


def test_estimated_price_text_openai_example():
    assert text.estimated_price_text(provider("openai")) == "Cost estimated at GPT-6 Astra's price"


def test_usage_cloud_line():
    totals = Totals(today=0.0012, month=0.031, requests_month=14)
    assert text.usage_text(provider("anthropic"), "", "", totals, None, 100) == (
        f"Today $0.0012 {MIDDLE_DOT} This month $0.0310 of $1.00 {MIDDLE_DOT} 14 requests")


def test_usage_cloud_line_singular_and_cap():
    totals = Totals(today=0.0, month=0.0, requests_month=1)
    assert text.usage_text(provider("openrouter"), "", "", totals, None, 2500) == (
        f"Today $0.0000 {MIDDLE_DOT} This month $0.0000 of $25.00 {MIDDLE_DOT} 1 request")


def test_usage_ollama_localhost_runs_locally():
    tokens = TokenTotals(today=1240, month=18900, requests_month=42)
    assert text.usage_text(provider("ollama"), "http://localhost:11434", "llama3.2:3b", None, tokens, 100) == (
        f"Today 1,240 tokens {MIDDLE_DOT} This month 18,900 tokens {MIDDLE_DOT} 42 requests "
        "(no cost: runs locally)")


@pytest.mark.parametrize("address, model", [
    ("http://ollama.example:11434", "llama3.2:3b"),
    ("http://localhost:11434", "gpt-oss:120b-cloud"),
    ("", ""),
])
def test_usage_ollama_not_local_is_not_tracked(address, model):
    tokens = TokenTotals(today=1240, month=18900, requests_month=42)
    line = text.usage_text(provider("ollama"), address, model, None, tokens, 100)
    assert line == f"Today 1,240 tokens {MIDDLE_DOT} This month 18,900 tokens {MIDDLE_DOT} 42 requests (cost not tracked)"
    assert "runs locally" not in line


def test_usage_other_is_never_runs_locally():
    tokens = TokenTotals(today=1240, month=18900, requests_month=42)
    for address in ("http://localhost:1234/v1", "http://lan.example:1234/v1"):
        line = text.usage_text(provider("other"), address, "", None, tokens, 100)
        assert line.endswith("42 requests (cost not tracked)")
        assert "runs locally" not in line


def test_module_has_no_qt_import():
    source = Path(text.__file__).read_text(encoding="utf-8")
    assert "PyQt6" not in source
