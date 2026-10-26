"""The per-provider model price table and the helpers that read it."""

from __future__ import annotations

import pytest

from proofline.ai_prices import (
    DEFAULT_MODEL,
    MODEL_IDS,
    cost,
    default_model,
    models_for,
    most_expensive,
    price_for,
)


@pytest.mark.parametrize("pid,model,inp,out", [
    ("anthropic", "claude-haiku-5-5", 0.10, 0.50),
    ("anthropic", "claude-sonnet-5-5", 2.00, 10.00),
    ("anthropic", "claude-opus-5-5", 4.00, 20.00),
    ("openai", "gpt-6-luna", 0.10, 0.50),
    ("openai", "gpt-6.1-sol", 2.00, 10.00),
    ("openai", "gpt-6-astra", 10.00, 50.00),
    ("gemini", "gemini-2.5-flash-lite", 0.10, 0.40),
    ("gemini", "gemini-3.5-flash-lite", 0.30, 2.50),
    ("gemini", "gemini-2.5-pro", 1.25, 10.00),
    ("grok", "grok-4.3", 1.25, 2.50),
    ("grok", "grok-4.5", 2.00, 6.00),
    ("grok", "grok-4.7", 2.00, 6.00),
    ("mistral", "mistral-small-2603", 0.15, 0.60),
    ("mistral", "mistral-large-4", 1.36, 4.18),
    ("mistral", "mistral-medium-3-5", 1.50, 7.50),
    ("deepseek", "deepseek-flash", 0.30, 1.20),
    ("deepseek", "deepseek-v4-pro", 1.32, 3.96),
    ("groq", "openai/gpt-oss-20b", 0.075, 0.30),
    ("groq", "openai/gpt-oss-120b", 0.15, 0.60),
])
def test_price_table(pid, model, inp, out):
    price = price_for(pid, model)
    assert (price.input_per_million, price.output_per_million) == (inp, out)


def test_models_per_provider_cheapest_first():
    assert [m.model_id for m in models_for("groq")] == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert default_model("mistral") == "mistral-small-2603" and default_model("ollama") == ""
    assert most_expensive("openai").model_id == "gpt-6-astra" and MODEL_IDS == (
        "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")
    assert DEFAULT_MODEL == "claude-haiku-5-5"


def test_unknown_model_has_no_price():
    assert price_for("openai", "gpt-x") is None
    assert price_for("nope", "gpt-6-luna") is None


def test_cost_takes_a_price():
    assert cost(price_for("openai", "gpt-6-luna"), 1_000_000, 1_000_000) == 0.6
    assert cost(price_for("anthropic", "claude-opus-5-5"), 1000, 500) == 0.014


def test_dearest_ranks_by_output_price_then_input_price():
    from proofline.ai_prices import ModelPrice, dearest

    a = ModelPrice("openrouter", "a", "A", 5.0, 1.0)
    b = ModelPrice("openrouter", "b", "B", 1.0, 9.0)
    c = ModelPrice("openrouter", "c", "C", 2.0, 9.0)
    assert dearest((a, b)) is b
    assert dearest((b, c)) is c
    assert dearest(()) is None


def test_dearest_takes_the_last_of_equal_maxima_in_table_order():
    from proofline.ai_prices import ModelPrice, dearest

    first = ModelPrice("grok", "older", "Older", 2.0, 6.0)
    last = ModelPrice("grok", "newer", "Newer", 2.0, 6.0)
    assert dearest((first, last)) is last
    assert dearest((last, first)) is first


@pytest.mark.parametrize("pid,expected", [
    ("anthropic", "claude-opus-5-5"),
    ("openai", "gpt-6-astra"),
    ("gemini", "gemini-2.5-pro"),
    ("grok", "grok-4.7"),
    ("mistral", "mistral-medium-3-5"),
    ("deepseek", "deepseek-v4-pro"),
    ("groq", "openai/gpt-oss-120b"),
])
def test_most_expensive_per_provider(pid, expected):
    assert most_expensive(pid).model_id == expected


def test_ollama_and_other_have_no_most_expensive_model():
    assert most_expensive("ollama") is None and most_expensive("other") is None
