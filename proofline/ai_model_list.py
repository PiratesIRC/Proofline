"""Live model lists: the models a provider's server offers, for the model choice on the AI page.

OpenRouter lists only models that accept structured outputs, with live prices. Ollama lists the
installed models. Other servers list the models under /models. Nothing here logs a URL, header or
key; errors come from ai_http, which keeps them safe to show.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx2

from proofline.ai_http import BEARER, get_json, make_client, message
from proofline.ai_prices import ModelPrice
from proofline.ai_providers import ProviderSpec, timeout_for
from proofline.ai_types import AiError

OPENROUTER = "openrouter"
OLLAMA = "ollama"
STRUCTURED_OUTPUTS = "structured_outputs"
PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelChoice:
    model_id: str
    label: str
    price: ModelPrice | None


def fetch_models(
    spec: ProviderSpec,
    base_url: str,
    key: str | None,
    transport: httpx2.BaseTransport | None = None,
) -> tuple[ModelChoice, ...]:
    """The models the provider offers, sorted by label; AiError when the list cannot be read.

    A key is dropped for a provider that takes none (Ollama) and for an empty or blank key, so it
    is never sent to a user-typed address by mistake.
    """
    key = _usable_key(spec, key)
    headers = {"Authorization": BEARER + key} if key else {}
    url, read = _source(spec, base_url)
    with make_client(timeout_for(spec), transport) as client:
        data = get_json(client, url, headers, spec.label, key is not None)
    return tuple(sorted(read(data, spec), key=lambda choice: choice.label.casefold()))


Reader = Callable[[dict, ProviderSpec], list[ModelChoice]]


def _usable_key(spec: ProviderSpec, key: str | None) -> str | None:
    """The key to send, or None when the provider takes no key or the key is empty or blank."""
    if spec.key == "none" or key is None or not key.strip():
        return None
    return key


def _source(spec: ProviderSpec, base_url: str) -> tuple[str, Reader]:
    """The list URL for the provider and the reader that turns its answer into choices."""
    if spec.id == OPENROUTER:
        return spec.base_url.rstrip("/") + "/models", _openrouter_choices
    if spec.id == OLLAMA:
        return base_url.rstrip("/") + "/api/tags", _ollama_choices
    return base_url.rstrip("/") + "/models", _other_choices


def _openrouter_choices(data: dict, spec: ProviderSpec) -> list[ModelChoice]:
    choices = []
    for entry in _entries(data, "data", spec):
        model_id = _text(entry.get("id"))
        if model_id is None or STRUCTURED_OUTPUTS not in _parameters(entry):
            continue
        label = _text(entry.get("name")) or model_id
        price = _openrouter_price(entry.get("pricing"), model_id, label)
        if price is not None:
            choices.append(ModelChoice(model_id, label, price))
    return choices


def _openrouter_price(pricing: Any, model_id: str, label: str) -> ModelPrice | None:
    """The price per million tokens; None (the model is skipped) when a price is missing or not a number."""
    if not isinstance(pricing, dict):
        return None
    prompt = _number(pricing.get("prompt"))
    completion = _number(pricing.get("completion"))
    if prompt is None or completion is None:
        return None
    return ModelPrice(OPENROUTER, model_id, label, prompt * PER_MILLION, completion * PER_MILLION)


def _ollama_choices(data: dict, spec: ProviderSpec) -> list[ModelChoice]:
    names = (_text(entry.get("name")) for entry in _entries(data, "models", spec))
    return [ModelChoice(name, name, None) for name in names if name is not None]


def _other_choices(data: dict, spec: ProviderSpec) -> list[ModelChoice]:
    ids = (_text(entry.get("id")) for entry in _entries(data, "data", spec))
    return [ModelChoice(model_id, model_id, None) for model_id in ids if model_id is not None]


def _entries(data: dict, field: str, spec: ProviderSpec) -> list[dict]:
    """The dict entries of the list under field; AiError bad_response when the list is missing."""
    items = data.get(field)
    if not isinstance(items, list):
        raise AiError("bad_response", message("bad_response", spec.label))
    return [item for item in items if isinstance(item, dict)]


def _parameters(entry: dict) -> list[Any]:
    parameters = entry.get("supported_parameters")
    return parameters if isinstance(parameters, list) else []


def _text(value: Any) -> str | None:
    """The value when it is a non-empty string, else None."""
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    """A finite, non-negative number from a JSON number or numeric string, else None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None
