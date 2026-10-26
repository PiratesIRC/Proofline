"""The AI providers Proofline can send suggestion requests to, and how to reach each one.

Cloud base URLs are fixed here and must be https. Ollama and Other take an address the user
types, checked by normalize_ai_address. This module imports nothing from proofline:
config.py and ai_prices.py depend on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_PROVIDER = "anthropic"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
LOCAL_TIMEOUT_SECONDS = 120.0  # a local model can be slow on first use
CLOUD_TIMEOUT_SECONDS = 20.0
KEY_SUFFIX = "api-key"
MODEL_NAME_PATTERN = re.compile(r"[A-Za-z0-9._:/-]{1,200}")
ADDRESS_SCHEMES = ("http", "https")
PORT_MESSAGE = "The address's port must be a number from 1 to 65535, or left out."


@dataclass(frozen=True, eq=False)
class ProviderSpec:
    id: str
    label: str
    protocol: str  # wire format: anthropic, openai, gemini or ollama
    base_url: str  # "" for Ollama and Other, whose address the user types
    key: str  # "required", "optional" or "none"
    json_mode: str  # "schema" (strict JSON schema) or "object" (any JSON object)
    max_tokens_field: str
    extra_body: tuple[tuple[str, object], ...]  # request fields the provider needs on every call
    local: bool  # runs on this PC or the LAN: longer timeout, no key
    priced: bool  # has a fixed price table in ai_prices
    tested: bool  # verified against the live service
    key_hint: str
    privacy_url: str


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec("anthropic", "Claude", "anthropic", "https://api.anthropic.com", "required", "schema",
                 "max_tokens", (), False, True, True, "console.anthropic.com",
                 "https://privacy.anthropic.com/"),
    ProviderSpec("openai", "OpenAI", "openai", "https://api.openai.com/v1", "required", "schema",
                 "max_completion_tokens", (("reasoning_effort", "low"),), False, True, False,
                 "platform.openai.com",
                 "https://developers.openai.com/api/docs/guides/your-data"),
    ProviderSpec("gemini", "Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta", "required",
                 "schema", "maxOutputTokens", (), False, True, False, "aistudio.google.com",
                 "https://ai.google.dev/gemini-api/terms"),
    ProviderSpec("grok", "Grok", "openai", "https://api.x.ai/v1", "required", "schema",
                 "max_completion_tokens", (("reasoning_effort", "low"),), False, True, False,
                 "console.x.ai", "https://docs.x.ai/developers/faq/security"),
    ProviderSpec("mistral", "Mistral", "openai", "https://api.mistral.ai/v1", "required", "schema",
                 "max_tokens", (), False, True, False, "console.mistral.ai",
                 "https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training"),
    ProviderSpec("deepseek", "DeepSeek", "openai", "https://api.deepseek.com", "required", "object",
                 "max_tokens", (("thinking", {"type": "disabled"}),), False, True, False,
                 "platform.deepseek.com",
                 "https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html"),
    ProviderSpec("groq", "Groq", "openai", "https://api.groq.com/openai/v1", "required", "schema",
                 "max_completion_tokens", (("reasoning_effort", "low"),), False, True, False,
                 "console.groq.com", "https://console.groq.com/docs/legal/services-agreement"),
    # priced=True means the spending limit applies, using live prices from OpenRouter's model list.
    ProviderSpec("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "required", "schema",
                 "max_tokens",
                 (("provider", {"require_parameters": True, "data_collection": "deny"}),),
                 False, True, False, "openrouter.ai", "https://openrouter.ai/privacy"),
    ProviderSpec("ollama", "Ollama", "ollama", "", "none", "schema", "num_predict", (), True, False, True,
                 "", ""),
    ProviderSpec("other", "Other server", "openai", "", "optional", "schema", "max_tokens", (), True, False,
                 False, "", ""),
)
PROVIDER_IDS = tuple(spec.id for spec in PROVIDERS)
_BY_ID = {spec.id: spec for spec in PROVIDERS}


def provider(pid: str) -> ProviderSpec:
    """The spec for pid; KeyError when pid is not a known provider."""
    return _BY_ID[pid]


def timeout_for(spec: ProviderSpec) -> float:
    """Seconds to wait for a reply: longer for local servers, which can be slow."""
    return LOCAL_TIMEOUT_SECONDS if spec.local else CLOUD_TIMEOUT_SECONDS


def key_target(pid: str, prefix: str = "Proofline") -> str:
    """The Windows Credential Manager target name for a provider's API key."""
    return f"{prefix}/{pid}-{KEY_SUFFIX}"


def is_valid_model_name(name: object) -> bool:
    """True for a model name typed or stored: letters, digits and . _ : / - up to 200 characters."""
    return isinstance(name, str) and MODEL_NAME_PATTERN.fullmatch(name) is not None


def normalize_ai_address(text: str) -> str:
    """The address without surrounding spaces or one trailing slash; ValueError if it is not
    an http or https address with a host, if its port is not a number from 1 to 65535 (or missing after
    a colon), if it has spaces inside, or if it carries a user name, query or fragment."""
    cleaned = text.strip().removesuffix("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ADDRESS_SCHEMES or not parsed.hostname:
        raise ValueError("The address must start with http:// or https:// and include a host.")
    if "@" in parsed.netloc or "?" in cleaned or "#" in cleaned:
        raise ValueError("The address must not include a user name, password, query or fragment.")
    if any(char.isspace() for char in cleaned):
        raise ValueError("The address must not contain spaces.")
    _check_port(parsed)
    return cleaned


def _check_port(parsed) -> None:
    """ValueError for a port that is not a number from 1 to 65535, or a colon with no port after it."""
    if parsed.netloc.endswith(":"):
        raise ValueError(PORT_MESSAGE)
    try:
        port = parsed.port
    except ValueError:  # urllib: not a number, or out of range
        raise ValueError(PORT_MESSAGE) from None
    if port == 0:
        raise ValueError(PORT_MESSAGE)
