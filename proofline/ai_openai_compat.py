"""The OpenAI-format backend: OpenAI, Grok, Mistral, DeepSeek, Groq, OpenRouter and Other server.

Every call is a POST to <base>/chat/completions. Schema mode sends a strict JSON schema;
object mode (DeepSeek, and Other server once it has refused schemas) asks for any JSON object and
puts the schema in the system prompt. Nothing here logs a URL, header, body or key.
"""

from __future__ import annotations

import json
import math

import httpx2

from proofline.ai_answers import parse_answer
from proofline.ai_http import make_client, message, post_json
from proofline.ai_providers import ProviderSpec, timeout_for
from proofline.ai_types import AiError, AiRequest, AiResult

OTHER_ID = "other"
SCHEMA_PROMPT = "\n\nAnswer only with json matching this JSON Schema: "
OPENROUTER_ID = "openrouter"
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/PiratesIRC/Proofline",
    "X-OpenRouter-Title": "Proofline",
}
REFUSED_SCHEMA_WORDS = ("response_format", "json_schema")
_OBJECT_MODE_ADDRESSES: set[str] = set()  # Other server addresses that refused json_schema


def forget_object_mode() -> None:
    """Forget every address that fell back to object mode (for tests)."""
    _OBJECT_MODE_ADDRESSES.clear()


class OpenAICompatBackend:
    def __init__(self, spec: ProviderSpec, key: str | None, base_url: str,
                 transport: httpx2.BaseTransport | None = None) -> None:
        self.spec = spec
        self.key = key or None
        self.base_url = base_url.rstrip("/")
        self.url = self.base_url + "/chat/completions"
        self.timeout = timeout_for(spec)
        self.transport = transport

    def send(self, request: AiRequest, model: str) -> AiResult:
        mode = self._mode()
        with make_client(self.timeout, self.transport) as client:
            try:
                data = self._post(client, request, model, mode)
            except AiError as exc:
                if mode != "schema" or not self._refused_schema(exc):
                    raise
                _OBJECT_MODE_ADDRESSES.add(self.base_url)
                data = self._post(client, request, model, "object")
        return _result(data, request.schema, self.spec.label, trusted_cost=self.spec.id == OPENROUTER_ID)

    def _mode(self) -> str:
        if self.spec.json_mode == "object":
            return "object"
        if self.spec.id == OTHER_ID and self.base_url in _OBJECT_MODE_ADDRESSES:
            return "object"
        return "schema"

    def _refused_schema(self, exc: AiError) -> bool:
        return (self.spec.id == OTHER_ID and exc.kind == "rejected"
                and any(word in exc.message for word in REFUSED_SCHEMA_WORDS))

    def _post(self, client: httpx2.Client, request: AiRequest, model: str, mode: str) -> dict:
        headers = self._headers()
        body = self._body(request, model, mode)
        return post_json(client, self.url, headers, body, self.spec.label, self.key is not None)

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.key is not None:
            headers["Authorization"] = f"Bearer {self.key}"
        if self.spec.id == OPENROUTER_ID:
            headers.update(OPENROUTER_HEADERS)
        return headers

    def _body(self, request: AiRequest, model: str, mode: str) -> dict:
        system = request.system
        body: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": request.text}],
            self.spec.max_tokens_field: request.max_tokens,
            **dict(self.spec.extra_body),
        }
        if mode == "object":
            body["messages"][0]["content"] = system + SCHEMA_PROMPT + json.dumps(request.schema)
            body["response_format"] = {"type": "json_object"}
        else:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": request.job, "strict": True, "schema": request.schema},
            }
        return body


def _result(data: dict, schema: dict, label: str, trusted_cost: bool) -> AiResult:
    """The first choice as an AiResult; a cut-off, a refusal or a malformed answer raises AiError."""
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _count(usage, "prompt_tokens")
    output_tokens = _count(usage, "completion_tokens")
    choice = _first_choice(data, label, input_tokens, output_tokens)
    reply = choice.get("message")
    reply = reply if isinstance(reply, dict) else {}
    if choice.get("finish_reason") == "length":
        raise AiError("bad_response", message("cut_off", label), input_tokens, output_tokens, cut_off=True)
    if reply.get("refusal"):
        raise AiError("refusal", message("refusal", label), input_tokens, output_tokens)
    content = reply.get("content")
    parsed = parse_answer(content if isinstance(content, str) else "", schema, label,
                          input_tokens, output_tokens)
    return AiResult(parsed, input_tokens, output_tokens, _cost(usage, trusted_cost))


def _first_choice(data: dict, label: str, input_tokens: int, output_tokens: int) -> dict:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AiError("bad_response", message("bad_response", label), input_tokens, output_tokens)
    return choices[0]


def _count(usage: dict, name: str) -> int:
    value = usage.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _cost(usage: dict, trusted: bool) -> float | None:
    """The dollars OpenRouter reports for the request. Any other server's figure is ignored, and so is a
    value that is not a finite, non-negative number; None means the price table decides."""
    if not trusted:
        return None
    value = usage.get("cost")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return float(value)
    return None
