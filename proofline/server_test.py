"""The Settings connection test: check a known-bad sentence and explain the result plainly.

The result has one of three levels:
- READY (green): the server answered and found the error in the test sentence.
- PROBLEM (orange): the server answered, but checking does not work.
- UNREACHABLE (red): no usable connection.
Pure logic apart from the HTTP call, which goes through LanguageToolClient.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass

from proofline.config import ConfigError, normalize_server_url, redact_url
from proofline.lt_client import (
    ERROR_CONNECT,
    ERROR_HTTP,
    ERROR_RESPONSE,
    ERROR_SSL,
    ERROR_TIMEOUT,
    LanguageToolClient,
    LanguageToolError,
)

log = logging.getLogger(__name__)

TEST_SENTENCE = "This are a test sentence."
HTTP_UNAUTHORIZED = frozenset({401, 403})
HTTP_NOT_FOUND = frozenset({404, 405})
HTTP_BAD_REQUEST = 400
HTTP_SERVER_ERROR_MIN = 500
LANGUAGE_ERROR_MARKER = "language"


class StatusLevel(enum.Enum):
    READY = "ready"
    PROBLEM = "problem"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ServerStatus:
    level: StatusLevel
    title: str
    detail: str = ""


READY = ServerStatus(StatusLevel.READY, "Ready", "Connected, and checking works.")
NOT_CORRECTED = ServerStatus(
    StatusLevel.PROBLEM, "Test sentence not corrected",
    "The server answered but found no mistake in “This are a test sentence.” Check the language setting.",
)


def run_server_test(url_text: str, language: str, client: LanguageToolClient | None = None) -> ServerStatus:
    """Normalise the address, check TEST_SENTENCE, and describe the outcome. Never raises."""
    try:
        url = normalize_server_url(url_text)
    except ConfigError as exc:
        return ServerStatus(StatusLevel.UNREACHABLE, "Address not valid", str(exc))
    client = client or LanguageToolClient(url, language or "auto")
    try:
        matches = client.check(TEST_SENTENCE)
    except LanguageToolError as exc:
        log.warning("Connection test failed: %s", exc)
        return describe_error(exc, redact_url(url))
    return READY if matches else NOT_CORRECTED


def describe_error(exc: LanguageToolError, safe_url: str) -> ServerStatus:
    """Translate a client error into a short title and one plain sentence."""
    if exc.kind == ERROR_CONNECT:
        return ServerStatus(StatusLevel.UNREACHABLE, "Can't connect",
                            f"Nothing answered at {safe_url}. Is the server running?")
    if exc.kind == ERROR_TIMEOUT:
        return ServerStatus(StatusLevel.UNREACHABLE, "No response", "The server didn't answer in time.")
    if exc.kind == ERROR_SSL:
        return ServerStatus(StatusLevel.UNREACHABLE, "Secure connection failed",
                          "Check that the address starts with the right http:// or https://.")
    if exc.kind == ERROR_HTTP:
        return _describe_http(exc.status or 0, exc.body)
    if exc.kind == ERROR_RESPONSE:
        return ServerStatus(StatusLevel.PROBLEM, "Not a LanguageTool server",
                            "Something answered, but not with LanguageTool results. Check the address.")
    return ServerStatus(StatusLevel.UNREACHABLE, "Connection failed", str(exc))


def _describe_http(status: int, body: str) -> ServerStatus:
    if status in HTTP_UNAUTHORIZED:
        return ServerStatus(StatusLevel.PROBLEM, "Password required",
                          "The server refused the request. Put the login in the address: https://user:password@host")
    if status in HTTP_NOT_FOUND:
        return ServerStatus(StatusLevel.PROBLEM, "Not a LanguageTool server",
                          f"The address answered with HTTP {status}. Check the path (usually ends in /v2).")
    if status == HTTP_BAD_REQUEST and LANGUAGE_ERROR_MARKER in body.casefold():
        return ServerStatus(StatusLevel.PROBLEM, "Language not available",
                          "This server doesn't support the chosen language. Try Auto-detect.")
    if status >= HTTP_SERVER_ERROR_MIN:
        return ServerStatus(StatusLevel.PROBLEM, "Server error", f"The server reported an error (HTTP {status}).")
    return ServerStatus(StatusLevel.PROBLEM, "Request rejected", f"The server answered with HTTP {status}.")
