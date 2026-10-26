"""The models Proofline offers for each AI provider, and what they cost.

Prices are dollars per million tokens (input, output). Claude's are from Anthropic's pricing
table (checked 2026-10-26). The DeepSeek rows are DeepSeek's PEAK rates: they could not be
confirmed on DeepSeek's pricing page as of 2026-10-26, and peak rates keep the spending limit
from under-counting. Check all rows again at each release; a model missing from MODELS cannot
be picked. Ollama and Other are unpriced. This module imports only ai_providers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from proofline.ai_providers import DEFAULT_PROVIDER

TOKENS_PER_PRICE_UNIT = 1_000_000
CHARS_PER_TOKEN_ESTIMATE = 3  # generous: real English text averages closer to 4
PROMPT_OVERHEAD_TOKENS = 200  # system prompt and output schema


@dataclass(frozen=True)
class ModelPrice:
    provider: str  # a provider id from ai_providers
    model_id: str
    label: str
    input_per_million: float  # dollars
    output_per_million: float  # dollars


MODELS: tuple[ModelPrice, ...] = (
    ModelPrice(DEFAULT_PROVIDER, "claude-haiku-5-5", "Haiku 5.5", 0.10, 0.50),
    ModelPrice(DEFAULT_PROVIDER, "claude-sonnet-5-5", "Sonnet 5.5", 2.00, 10.00),
    ModelPrice(DEFAULT_PROVIDER, "claude-opus-5-5", "Opus 5.5", 4.00, 20.00),
    ModelPrice("openai", "gpt-6-luna", "GPT-6 Luna", 0.10, 0.50),
    ModelPrice("openai", "gpt-6.1-sol", "GPT-6.1 Sol", 2.00, 10.00),
    ModelPrice("openai", "gpt-6-astra", "GPT-6 Astra", 10.00, 50.00),
    ModelPrice("gemini", "gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", 0.10, 0.40),
    ModelPrice("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", 0.30, 2.50),
    ModelPrice("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro", 1.25, 10.00),
    ModelPrice("grok", "grok-4.3", "Grok 4.3", 1.25, 2.50),
    ModelPrice("grok", "grok-4.5", "Grok 4.5", 2.00, 6.00),
    ModelPrice("grok", "grok-4.7", "Grok 4.7", 2.00, 6.00),
    ModelPrice("mistral", "mistral-small-2603", "Mistral Small 4", 0.15, 0.60),
    ModelPrice("mistral", "mistral-large-4", "Mistral Large 4", 1.36, 4.18),
    ModelPrice("mistral", "mistral-medium-3-5", "Mistral Medium 3.5", 1.50, 7.50),
    ModelPrice("deepseek", "deepseek-flash", "DeepSeek Flash", 0.30, 1.20),
    ModelPrice("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", 1.32, 3.96),
    ModelPrice("groq", "openai/gpt-oss-20b", "GPT-OSS 20B", 0.075, 0.30),
    ModelPrice("groq", "openai/gpt-oss-120b", "GPT-OSS 120B", 0.15, 0.60),
)
MODEL_IDS = tuple(model.model_id for model in MODELS if model.provider == DEFAULT_PROVIDER)
DEFAULT_MODEL = "claude-haiku-5-5"


def models_for(pid: str) -> tuple[ModelPrice, ...]:
    """The priced models for provider pid, cheapest first (by input, then output price)."""
    rows = [model for model in MODELS if model.provider == pid]
    return tuple(sorted(rows, key=lambda model: (model.input_per_million, model.output_per_million)))


def default_model(pid: str) -> str:
    """The cheapest model for pid, or "" when the provider has no priced models."""
    models = models_for(pid)
    return models[0].model_id if models else ""


def dearest(prices: Iterable[ModelPrice]) -> ModelPrice | None:
    """The dearest of prices: the highest output price, ties broken by input price; None when empty.
    Output tokens set most of a request's worst case (max_tokens), so they rank first. When two rows tie
    on both, the one listed last wins (the newer model in the table). This is the one "most expensive"
    rule: the spending check and the price note both use it."""
    best = None
    for price in prices:
        if best is None or _rank(price) >= _rank(best):
            best = price
    return best


def _rank(price: ModelPrice) -> tuple[float, float]:
    return price.output_per_million, price.input_per_million


def most_expensive(pid: str) -> ModelPrice | None:
    """The dearest priced model for pid (see dearest); None if pid has none."""
    return dearest(models_for(pid))


def price_for(pid: str, model_id: str) -> ModelPrice | None:
    return next((m for m in MODELS if m.provider == pid and m.model_id == model_id), None)


def cost(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    """Dollars for one request at price."""
    dollars = (input_tokens * price.input_per_million + output_tokens * price.output_per_million)
    return round(dollars / TOKENS_PER_PRICE_UNIT, 6)


def estimate_input_tokens(text: str) -> int:
    """An over-estimate of the input tokens for text, for the worst-case cost check."""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE + PROMPT_OVERHEAD_TOKENS
