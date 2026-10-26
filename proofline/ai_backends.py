"""Picks the backend for a provider: one class per wire format, chosen from the provider's spec.

Ollama never takes a key (it is ignored). Other takes the address the user typed; every other
OpenAI-format provider uses its fixed base address from ai_providers.
"""

from __future__ import annotations

from proofline.ai_client import AnthropicBackend
from proofline.ai_gemini import GeminiBackend
from proofline.ai_ollama import OllamaBackend
from proofline.ai_openai_compat import OTHER_ID, OpenAICompatBackend
from proofline.ai_providers import ProviderSpec
from proofline.ai_types import AiBackend


def make_backend(spec: ProviderSpec, key: str | None, base_url: str) -> AiBackend:
    if spec.protocol == "anthropic":
        return AnthropicBackend(key or "")
    if spec.protocol == "gemini":
        return GeminiBackend(spec, key or "")
    if spec.protocol == "ollama":
        return OllamaBackend(spec, base_url)
    address = base_url if spec.id == OTHER_ID else spec.base_url
    return OpenAICompatBackend(spec, key, address)
