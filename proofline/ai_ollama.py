"""The Ollama backend: native /api/chat with the schema as the output format.

Ollama runs on this PC or the LAN and takes no key. Thinking is switched off and the context
window is set explicitly, because Ollama's default context is smaller than a long page needs.
Nothing here logs a URL, header, body or key.
"""

from __future__ import annotations

import httpx2

from proofline.ai_answers import parse_answer
from proofline.ai_http import make_client, post_json
from proofline.ai_providers import ProviderSpec, timeout_for
from proofline.ai_types import AiError, AiRequest, AiResult
from proofline.config import redact_url

NUM_CTX = 8192
NOT_FOUND_TEMPLATE = "Ollama has no model named {model}. Press Refresh to see the installed models."
NOT_RUNNING_TEMPLATE = "Could not reach Ollama at {address}. Is it running?"


class OllamaBackend:
    def __init__(self, spec: ProviderSpec, base_url: str, transport: httpx2.BaseTransport | None = None) -> None:
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.url = self.base_url + "/api/chat"
        self.timeout = timeout_for(spec)
        self.transport = transport

    def send(self, request: AiRequest, model: str) -> AiResult:
        overrides = {404: AiError("rejected", NOT_FOUND_TEMPLATE.format(model=model))}
        network_message = NOT_RUNNING_TEMPLATE.format(address=redact_url(self.base_url))
        with make_client(self.timeout, self.transport) as client:
            data = post_json(
                client, self.url, {}, _body(request, model), self.spec.label, False,
                overrides=overrides, network_message=network_message,
            )
        return _result(data, request.schema, self.spec.label)


def _body(request: AiRequest, model: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.text}],
        "stream": False,
        "format": request.schema,
        "think": False,
        "options": {"num_ctx": NUM_CTX, "num_predict": request.max_tokens},
    }


def _result(data: dict, schema: dict, label: str) -> AiResult:
    reply = data.get("message")
    reply = reply if isinstance(reply, dict) else {}
    content = reply.get("content")
    input_tokens = _count(data, "prompt_eval_count")
    output_tokens = _count(data, "eval_count")
    parsed = parse_answer(content if isinstance(content, str) else "", schema, label,
                          input_tokens, output_tokens)
    return AiResult(parsed, input_tokens, output_tokens)


def _count(data: dict, name: str) -> int:
    value = data.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
