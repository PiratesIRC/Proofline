"""HTTP calls for the AI providers: one client setting, JSON in and out, and the error kinds.

Every failure becomes an AiError whose message is safe to show. Nothing here logs or puts a URL,
header, request body or key into a message, and httpx errors are dropped (raise ... from None)
because their text can carry the URL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import httpx2

from proofline.ai_providers import CLOUD_TIMEOUT_SECONDS
from proofline.ai_types import AiError

log = logging.getLogger(__name__)

CREDIT_CODE = "credit_balance_exhausted"
KEY_HINTS = ("API key", "API_KEY")
DETAIL_LIMIT = 200  # characters of the provider's own error text shown to the user
MIN_SECRET_CHARS = 8  # shorter header values are not treated as keys when scanning provider text
BEARER = "Bearer "
CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "x-goog-api-key", "api-key"})
TEMPLATES = {
    "auth": "{label} did not accept the API key.",
    "credit": "{label} says the account is out of credit.",
    "rate_limit": "{label} is limiting requests. Try again in a minute.",
    "timeout": "{label} took longer than {seconds:g} seconds. Try again.",
    "network": "Could not reach {label}.",
    "server": "{label} had a problem. Try again.",
    "bad_response": "{label}'s answer could not be read.",
    "cut_off": "{label}'s answer was cut off.",
    "refusal": "{label} declined this request.",
    "rejected": "{label} refused the request (HTTP {status}).",
}


def message(kind: str, label: str, seconds: float = CLOUD_TIMEOUT_SECONDS, detail: str = "", status: int = 0) -> str:
    """The user-facing text for an error kind; detail is the provider's own explanation."""
    if kind == "rejected" and detail:
        return f"{label} refused the request: {detail}"
    return TEMPLATES[kind].format(label=label, seconds=seconds, status=status)


def make_client(timeout: float, transport: httpx2.BaseTransport | None = None) -> httpx2.Client:
    """A client that never follows redirects and ignores proxy environment variables."""
    return httpx2.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport)


def post_json(
    client: httpx2.Client,
    url: str,
    headers: Mapping[str, str],
    body: Any,
    label: str,
    key_sent: bool,
    *,
    overrides: Mapping[int, AiError] | None = None,
    network_message: str = "",
    key_hint_400: bool = False,
) -> dict:
    """POST body as JSON and return the 2xx JSON object; otherwise raise AiError."""
    return _exchange(
        lambda: client.post(url, headers=headers, json=body),
        client,
        label,
        key_sent,
        overrides,
        network_message,
        _credentials(headers),
        key_hint_400,
    )


def get_json(
    client: httpx2.Client,
    url: str,
    headers: Mapping[str, str],
    label: str,
    key_sent: bool,
    *,
    overrides: Mapping[int, AiError] | None = None,
    network_message: str = "",
    key_hint_400: bool = False,
) -> dict:
    """GET url and return the 2xx JSON object; otherwise raise AiError."""
    return _exchange(
        lambda: client.get(url, headers=headers),
        client,
        label,
        key_sent,
        overrides,
        network_message,
        _credentials(headers),
        key_hint_400,
    )


def _exchange(
    send: Callable[[], httpx2.Response],
    client: httpx2.Client,
    label: str,
    key_sent: bool,
    overrides: Mapping[int, AiError] | None,
    network_message: str,
    secrets: tuple[str, ...],
    key_hint_400: bool,
) -> dict:
    seconds = client.timeout.read or CLOUD_TIMEOUT_SECONDS
    try:
        response = send()
    except httpx2.TimeoutException:
        raise AiError("timeout", message("timeout", label, seconds=seconds)) from None
    except httpx2.HTTPError:
        raise AiError("network", network_message or message("network", label)) from None
    return _answer(response, label, key_sent, overrides or {}, seconds, secrets, key_hint_400)


def _answer(
    response: httpx2.Response,
    label: str,
    key_sent: bool,
    overrides: Mapping[int, AiError],
    seconds: float,
    secrets: tuple[str, ...],
    key_hint_400: bool,
) -> dict:
    status = response.status_code
    if 200 <= status < 300:
        return _json_object(response, label)
    if status in overrides:
        raise overrides[status]
    if 300 <= status < 400:
        raise AiError("rejected", message("rejected", label, status=status))
    log.warning("%s answered HTTP %d", label, status)
    raise error_for(label, status, _json_or_none(response), key_sent, seconds, secrets=secrets,
                    key_hint_400=key_hint_400)


def _json_object(response: httpx2.Response, label: str) -> dict:
    data = _json_or_none(response)
    if not isinstance(data, dict):
        raise AiError("bad_response", message("bad_response", label))
    return data


def _json_or_none(response: httpx2.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def error_for(
    label: str,
    status: int,
    body: Any,
    key_sent: bool,
    timeout: float = CLOUD_TIMEOUT_SECONDS,
    *,
    secrets: tuple[str, ...] = (),
    key_hint_400: bool = False,
) -> AiError:
    """The AiError for a non-2xx answer, from its status and JSON body.

    secrets are the request's header values; provider text that repeats one (or a bearer token
    without its prefix) is dropped, and long text is cut to DETAIL_LIMIT characters. key_hint_400 is
    True only for Gemini, the one provider that reports a bad key as HTTP 400 with "API key" in the text.
    """
    raw_detail, code = _error_fields(body)
    kind = _kind(status, raw_detail, code, key_sent, key_hint_400)  # classified on the provider's own text
    shown = _shown_detail(raw_detail, secrets)  # sanitized only for the message
    return AiError(kind, message(kind, label, seconds=timeout, detail=shown, status=status))


def _shown_detail(detail: str, secrets: tuple[str, ...]) -> str:
    needles = [part for raw in secrets for part in (raw, raw.removeprefix(BEARER)) if len(part) >= MIN_SECRET_CHARS]
    if any(needle in detail for needle in needles):
        return ""
    if len(detail) > DETAIL_LIMIT:
        return detail[:DETAIL_LIMIT] + "..."
    return detail


def _credentials(headers: Mapping[str, str]) -> tuple[str, ...]:
    """The values of credential headers only; other header values (content types and so on) are not secrets."""
    return tuple(value for name, value in headers.items() if name.lower() in CREDENTIAL_HEADERS)


def _kind(status: int, detail: str, code: str, key_sent: bool, key_hint_400: bool) -> str:
    key_400 = status == 400 and key_hint_400 and any(hint in detail for hint in KEY_HINTS)
    if status in (401, 403) or key_400:
        return "auth" if key_sent else "rejected"
    if status == 402 or (status == 429 and code == CREDIT_CODE):
        return "credit"
    if status == 429:
        return "rate_limit"
    if 500 <= status < 600:
        return "server"
    return "rejected"


def _error_fields(body: Any) -> tuple[str, str]:
    """The provider's error text and error code, each empty when absent."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, str):
        return error.strip(), ""
    if not isinstance(error, dict):
        return "", ""
    text = error.get("message")
    code = error.get("code")
    return (text.strip() if isinstance(text, str) else ""), (code if isinstance(code, str) else "")
