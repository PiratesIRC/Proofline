"""HTTP client for the LanguageTool /v2/check API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from proofline.config import redact_url

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 10
MAX_REPLACEMENTS = 5
MAX_ERROR_BODY_CHARS = 200
BMP_MAX_CODEPOINT = 0xFFFF
PICKY_LEVEL = "picky"

# LanguageToolError.kind values: what went wrong, for callers that explain it to the user.
ERROR_TIMEOUT = "timeout"
ERROR_SSL = "ssl"
ERROR_CONNECT = "connect"
ERROR_REQUEST = "request"
ERROR_HTTP = "http"
ERROR_RESPONSE = "response"


class LanguageToolError(Exception):
    """Raised when the server cannot be reached or returns an unusable response.

    `kind` is one of the ERROR_* constants; `status` and `body` are set for ERROR_HTTP.
    """

    def __init__(self, message: str, kind: str = ERROR_REQUEST, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.body = body


@dataclass(frozen=True)
class Match:
    """A reported issue. offset/length are Python string indices into the checked text."""

    offset: int
    length: int
    message: str
    short_message: str
    replacements: tuple[str, ...]
    rule_id: str
    category: str
    error_text: str
    category_id: str = ""


class LanguageToolClient:
    def __init__(
        self,
        server_url: str,
        language: str = "auto",
        session: requests.Session | None = None,
        timeout: float = REQUEST_TIMEOUT_S,
        disabled_rules: tuple[str, ...] = (),
        disabled_categories: tuple[str, ...] = (),
        picky: bool = False,
    ) -> None:
        self._server_url = server_url
        self._language = language
        self._session = session or requests.Session()
        self._timeout = timeout
        self._disabled_rules = disabled_rules
        self._disabled_categories = disabled_categories
        self._picky = picky

    def _form_data(self, text: str) -> dict[str, str]:
        """Build the POST form; optional keys are added only when they change server behaviour."""
        data = {"text": text, "language": self._language}
        if self._disabled_rules:
            data["disabledRules"] = ",".join(self._disabled_rules)
        if self._disabled_categories:
            data["disabledCategories"] = ",".join(self._disabled_categories)
        if self._picky:
            data["level"] = PICKY_LEVEL
        return data

    def check(self, text: str) -> tuple[Match, ...]:
        """Check text and return the matches LanguageTool reports."""
        if not text.strip():
            return ()
        safe_url = redact_url(self._server_url)
        log.debug("Checking %d chars at %s", len(text), safe_url)
        try:
            response = self._session.post(
                self._server_url,
                data=self._form_data(text),
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            log.warning("Request to %s timed out: %s", safe_url, exc)
            raise LanguageToolError(
                f"No response from {safe_url} within {self._timeout:g} seconds.", ERROR_TIMEOUT
            ) from exc
        except requests.exceptions.SSLError as exc:
            log.warning("Secure connection to %s failed: %s", safe_url, exc)
            raise LanguageToolError(
                f"Secure connection to {safe_url} failed. Check the address and the server's certificate.", ERROR_SSL
            ) from exc
        except requests.ConnectionError as exc:
            log.warning("Could not connect to %s: %s", safe_url, exc)
            raise LanguageToolError(
                f"Could not connect to {safe_url}. Check the URL and that the server is running.", ERROR_CONNECT
            ) from exc
        except requests.RequestException as exc:
            log.warning("Request to %s failed: %s", safe_url, exc)
            raise LanguageToolError(f"Could not reach LanguageTool server: {exc}") from exc

        if response.status_code != 200:
            body = response.text[:MAX_ERROR_BODY_CHARS]
            log.warning("%s returned HTTP %d: %s", safe_url, response.status_code, body)
            raise LanguageToolError(
                f"Server returned HTTP {response.status_code}: {body}", ERROR_HTTP, response.status_code, body
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise LanguageToolError("Server response was not valid JSON.", ERROR_RESPONSE) from exc

        matches = parse_matches(payload, text)
        log.debug("Server reported %d matches", len(matches))
        return matches


def utf16_index_map(text: str) -> list[int]:
    """Map UTF-16 code-unit offsets to Python string indices.

    The Java server counts characters outside the Basic Multilingual Plane
    (e.g. emoji) as two units; Python counts them as one. The returned list has
    one entry per UTF-16 unit plus a final entry for the end of the text.
    """
    mapping: list[int] = []
    for index, char in enumerate(text):
        units = 2 if ord(char) > BMP_MAX_CODEPOINT else 1
        mapping.extend([index] * units)
    mapping.append(len(text))
    return mapping


def parse_matches(payload: Any, text: str) -> tuple[Match, ...]:
    """Convert a /v2/check JSON payload into Match objects, skipping malformed entries."""
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise LanguageToolError("Server response is missing the 'matches' list.", ERROR_RESPONSE)
    index_map = utf16_index_map(text)
    parsed = (_parse_match(item, text, index_map) for item in payload["matches"])
    return tuple(m for m in parsed if m is not None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_match(item: Any, text: str, index_map: list[int]) -> Match | None:
    if not isinstance(item, dict):
        log.warning("Skipping non-object match: %r", item)
        return None
    try:
        unit_offset = int(item["offset"])
        unit_length = int(item["length"])
    except (KeyError, TypeError, ValueError):
        log.warning("Skipping match without valid offset/length: %r", item)
        return None
    unit_end = unit_offset + unit_length
    if unit_offset < 0 or unit_length < 0 or unit_end >= len(index_map):
        log.warning("Skipping match outside text bounds: offset=%d length=%d", unit_offset, unit_length)
        return None

    start, end = index_map[unit_offset], index_map[unit_end]
    raw_replacements = item.get("replacements")
    replacement_items = raw_replacements if isinstance(raw_replacements, list) else []
    replacements = tuple(
        r["value"]
        for r in replacement_items
        if isinstance(r, dict) and isinstance(r.get("value"), str)
    )[:MAX_REPLACEMENTS]
    rule = _as_dict(item.get("rule"))
    category = _as_dict(rule.get("category"))
    category_id = category.get("id")
    return Match(
        offset=start,
        length=end - start,
        message=str(item.get("message", "")),
        short_message=str(item.get("shortMessage", "")),
        replacements=replacements,
        rule_id=str(rule.get("id", "")),
        category=str(category.get("name", "")),
        error_text=text[start:end],
        category_id=category_id if isinstance(category_id, str) else "",
    )
