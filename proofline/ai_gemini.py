"""The Gemini backend: native generateContent with a JSON response schema.

The key travels only in the x-goog-api-key header, never in the URL. Nothing here logs a URL,
header, body or key.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx2

from proofline.ai_answers import parse_answer, schema_without_additional_properties
from proofline.ai_http import make_client, message, post_json
from proofline.ai_providers import ProviderSpec, timeout_for
from proofline.ai_types import AiError, AiRequest, AiResult

KEY_HEADER = "x-goog-api-key"
THINKING_CONFIG = {
    "gemini-3.5-flash-lite": {"thinkingLevel": "minimal"},
    "gemini-2.5-pro": {"thinkingLevel": "low"},
}
REFUSAL_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"})


class GeminiBackend:
    def __init__(self, spec: ProviderSpec, key: str, transport: httpx2.BaseTransport | None = None) -> None:
        self.spec = spec
        self.key = key or None
        self.base_url = spec.base_url.rstrip("/")
        self.timeout = timeout_for(spec)
        self.transport = transport

    def send(self, request: AiRequest, model: str) -> AiResult:
        url = f"{self.base_url}/models/{quote(model, safe='')}:generateContent"
        headers = {KEY_HEADER: self.key} if self.key is not None else {}
        body = _body(request, model)
        with make_client(self.timeout, self.transport) as client:
            data = post_json(client, url, headers, body, self.spec.label, self.key is not None,
                             key_hint_400=True)  # Gemini reports a bad key as HTTP 400
        return _result(data, request.schema, self.spec.label)


def _body(request: AiRequest, model: str) -> dict:
    generation: dict[str, Any] = {
        "responseMimeType": "application/json",
        "responseSchema": schema_without_additional_properties(request.schema),
        "maxOutputTokens": request.max_tokens,
    }
    if model in THINKING_CONFIG:
        generation["thinkingConfig"] = THINKING_CONFIG[model]
    return {
        "systemInstruction": {"parts": [{"text": request.system}]},
        "contents": [{"role": "user", "parts": [{"text": request.text}]}],
        "generationConfig": generation,
    }


def _result(data: dict, schema: dict, label: str) -> AiResult:
    """The first candidate's text as an AiResult; a block, a refusal or a cut-off raises AiError."""
    usage = data.get("usageMetadata")
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _count(usage, "promptTokenCount")
    output_tokens = _count(usage, "candidatesTokenCount") + _count(usage, "thoughtsTokenCount")
    feedback = data.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise AiError("refusal", message("refusal", label), input_tokens, output_tokens)
    candidate = _first_candidate(data, label)
    reason = candidate.get("finishReason")
    if reason in REFUSAL_REASONS:
        raise AiError("refusal", message("refusal", label), input_tokens, output_tokens)
    if reason == "MAX_TOKENS":
        raise AiError("bad_response", message("cut_off", label), input_tokens, output_tokens, cut_off=True)
    text = _joined_text(candidate)
    parsed = parse_answer(text, schema, label, input_tokens, output_tokens)
    return AiResult(parsed, input_tokens, output_tokens)


def _first_candidate(data: dict, label: str) -> dict:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise AiError("bad_response", message("bad_response", label))
    return candidates[0]


def _joined_text(candidate: dict) -> str:
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    return "".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))


def _count(usage: dict, name: str) -> int:
    value = usage.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
