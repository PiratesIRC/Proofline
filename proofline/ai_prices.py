"""Claude models Proofline offers and what they cost.

Prices are per million tokens, from Anthropic's pricing table (checked 2026-10-26). Check them
again at each release; a model missing from MODELS cannot be picked. This module imports
nothing from proofline so config.py can use it.
"""

from __future__ import annotations

from dataclasses import dataclass

TOKENS_PER_PRICE_UNIT = 1_000_000
CHARS_PER_TOKEN_ESTIMATE = 3  # generous: real English text averages closer to 4
PROMPT_OVERHEAD_TOKENS = 200  # system prompt and output schema


@dataclass(frozen=True)
class ModelPrice:
    model_id: str
    label: str
    input_per_million: float  # dollars
    output_per_million: float  # dollars


MODELS: tuple[ModelPrice, ...] = (
    ModelPrice("claude-haiku-5-5", "Haiku 5.5", 0.10, 0.50),
    ModelPrice("claude-sonnet-5-5", "Sonnet 5.5", 2.00, 10.00),
    ModelPrice("claude-opus-5-5", "Opus 5.5", 4.00, 20.00),
)
MODEL_IDS = tuple(model.model_id for model in MODELS)
DEFAULT_MODEL = "claude-haiku-5-5"


def price_for(model_id: str) -> ModelPrice | None:
    return next((model for model in MODELS if model.model_id == model_id), None)


def cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Dollars for one request; raises KeyError for a model with no price."""
    price = price_for(model_id)
    if price is None:
        raise KeyError(model_id)
    dollars = (input_tokens * price.input_per_million + output_tokens * price.output_per_million)
    return round(dollars / TOKENS_PER_PRICE_UNIT, 6)


def estimate_input_tokens(text: str) -> int:
    """An over-estimate of the input tokens for text, for the worst-case cost check."""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE + PROMPT_OVERHEAD_TOKENS
