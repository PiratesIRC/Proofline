"""Wording for the Settings AI page: provider names, key and address text, privacy and usage lines.

Pure functions with no Qt import, so the wording is tested without a window. The strings come from
docs/design/2026-10-26-ai-providers-design.md ("Settings AI page"). Where a line depends on the
address, "localhost" means the address's host is in config.LOOPBACK_HOSTS.
"""

from __future__ import annotations

from urllib.parse import urlparse

from proofline.ai_prices import ModelPrice, dearest, most_expensive
from proofline.ai_providers import ProviderSpec
from proofline.ai_usage import TokenTotals, Totals
from proofline.config import LOOPBACK_HOSTS, is_insecure_remote

CENTS_PER_DOLLAR = 100
MIDDLE_DOT = "\u00b7"
UNTESTED_TEXT = "(untested)"
UNTESTED_NOTE = ("This provider has not been tested with a real account yet. If something does not work, "
                 "please report it on GitHub.")
KEY_PLACEHOLDER = "Paste your API key"
OTHER_MODEL_TEXT = "Other model..."
RESAVE_KEY_TEXT = "Save the key again to use it with this address."
KEY_REFUSED_INSECURE = "Use https, or turn off the server's key requirement on a trusted network."
INSECURE_TEXT = "This address is not encrypted, so your text can be read on the network."
ADDRESS_DESCRIPTION = {
    "ollama": "Ollama's default is http://localhost:11434",
    "other": "The server's OpenAI-compatible address, such as http://localhost:1234/v1",
}
OTHER_KEY_DESCRIPTION = "Only if your server asks for one"
KEY_STORAGE_TEXT = "Kept in Windows Credential Manager, not in the settings file"
CLOUD_PRIVACY = ("When you ask for an AI suggestion, or press Test, Proofline sends that text (Test sends a "
                 "short fixed sentence) to {label} with your key. Nothing is sent otherwise.")
OPENROUTER_REFRESH = "Refreshing the model list also contacts {label}."
LOCAL_PRIVACY = "Your text stays on this computer."
LAN_PRIVACY = "Your text goes to the computer at this address."
CLOUD_MODEL_PRIVACY = "Your text goes to Ollama's servers for this model."
OTHER_PRIVACY = "Your text, and your key if you saved one, go to the server at this address."
WARNINGS = {
    "gemini": ("With a free Gemini key, Google may use your text to improve its products and people may read it. "
               "Paid keys are covered by different terms."),
    "mistral": ("Mistral may use API data from free accounts for training. Check the privacy settings in your "
                "Mistral console."),
    "openrouter": ("Requests go to the company running the model you pick. Proofline asks OpenRouter to skip "
                   "companies that store or train on your text."),
    "deepseek": "DeepSeek's general privacy policy says it stores data on servers in China.",
}
OLLAMA_CLOUD_SUFFIXES = ("-cloud", ":cloud")  # convention unverified: how Ollama marks its cloud models
LOCAL_USAGE_NOTE = "(no cost: runs locally)"
UNTRACKED_USAGE_NOTE = "(cost not tracked)"


def provider_item_text(spec: ProviderSpec) -> str:
    """The drop-down entry: the label, plus "(untested)" for a provider not checked with a real account."""
    return spec.label if spec.tested else f"{spec.label} {UNTESTED_TEXT}"


def key_title(spec: ProviderSpec) -> str:
    return f"{spec.label} API key"


def key_description(spec: ProviderSpec) -> str:
    if spec.id == "other":
        return OTHER_KEY_DESCRIPTION
    if spec.key == "none":
        return ""
    return f"From {spec.key_hint}. {KEY_STORAGE_TEXT}"


def is_ollama_cloud_model(model: str) -> bool:
    return model.endswith(OLLAMA_CLOUD_SUFFIXES)


def _is_local_address(address: str) -> bool:
    return (urlparse(address).hostname or "") in LOOPBACK_HOSTS


def _runs_locally(spec: ProviderSpec, address: str, model: str) -> bool:
    return spec.id == "ollama" and _is_local_address(address) and not is_ollama_cloud_model(model)


def privacy_text(spec: ProviderSpec, address: str, model: str = "") -> str:
    """The main privacy line for the selected provider."""
    if spec.id == "ollama":
        if is_ollama_cloud_model(model):
            return CLOUD_MODEL_PRIVACY
        return LOCAL_PRIVACY if _is_local_address(address) else LAN_PRIVACY
    if spec.id == "other":
        return OTHER_PRIVACY
    line = CLOUD_PRIVACY.format(label=spec.label)
    if spec.id == "openrouter":
        line += " " + OPENROUTER_REFRESH.format(label=spec.label)
    return line


def warning_text(spec: ProviderSpec) -> str:
    """The extra line for providers whose data terms need a warning; "" for the rest."""
    return WARNINGS.get(spec.id, "")


def insecure_text(address: str) -> str:
    """The unencrypted-address warning; "" unless text would travel over plain http to another host."""
    return INSECURE_TEXT if is_insecure_remote(address) else ""


def estimated_price_text(spec: ProviderSpec, live_prices: tuple[ModelPrice, ...] = ()) -> str:
    """The note under the spending limit for a typed model: priced at the provider's most expensive model.

    OpenRouter has no fixed table, so its most expensive model comes from live_prices (the fetched list).
    """
    priciest = dearest(live_prices) if spec.id == "openrouter" else most_expensive(spec.id)
    return f"Cost estimated at {priciest.label}'s price" if priciest else ""


def _requests(count: int) -> str:
    return f"{count} {'request' if count == 1 else 'requests'}"


def _cloud_usage(totals: Totals, cap_cents: int) -> str:
    return (f"Today ${totals.today:.4f} {MIDDLE_DOT} This month ${totals.month:.4f} of "
            f"${cap_cents / CENTS_PER_DOLLAR:.2f} {MIDDLE_DOT} {_requests(totals.requests_month)}")


def _token_usage(tokens: TokenTotals, note: str) -> str:
    return (f"Today {tokens.today:,} tokens {MIDDLE_DOT} This month {tokens.month:,} tokens {MIDDLE_DOT} "
            f"{_requests(tokens.requests_month)} {note}")


def usage_text(spec: ProviderSpec, address: str, model: str, totals: Totals | None,
               tokens: TokenTotals | None, cap_cents: int) -> str:
    """The usage line: dollars and the limit for cloud providers, tokens and requests otherwise."""
    if spec.priced:
        return _cloud_usage(totals, cap_cents)
    note = LOCAL_USAGE_NOTE if _runs_locally(spec, address, model) else UNTRACKED_USAGE_NOTE
    return _token_usage(tokens, note)
