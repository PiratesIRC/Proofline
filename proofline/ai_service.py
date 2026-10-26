"""Sends AI requests one at a time, within the monthly spending limit, and records their cost.

Runs on the GUI thread; the HTTP call itself goes to the Qt thread pool. Every request is
checked first: AI turned on, a key saved, the text short enough, no other request running,
and this month's recorded cost plus the request's worst case within the limit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from proofline.ai_client import (
    MAX_INPUT_CHARS,
    AiBackend,
    AiError,
    AiRequest,
    AiResult,
    AnthropicBackend,
)
from proofline.ai_keys import load_key
from proofline.ai_prices import cost, estimate_input_tokens
from proofline.ai_usage import (
    LEDGER_PATH,
    Totals,
    UsageEntry,
    can_spend,
    read_entries,
    record,
    totals,
)
from proofline.config import Config
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

OFF_MESSAGE = "AI is turned off in Settings."
NO_KEY_MESSAGE = "Add an API key in Settings, AI."
BUSY_MESSAGE = "Another AI request is still running."
TOO_LONG_MESSAGE = "Select a shorter part (at most 8,000 characters)."
CAP_MESSAGE = "Monthly AI limit reached."
FAILED_MESSAGE = "The AI request failed."
UNKNOWN_OUTCOME_KINDS = ("timeout", "network", "server")  # sent, maybe billed, no token counts back
CENTS_PER_DOLLAR = 100


class AiService(QObject):
    finished = pyqtSignal(object, object)  # AiRequest, AiResult
    failed = pyqtSignal(object, str, str)  # AiRequest, one-line message for the user, kind (see _refusal)

    def __init__(
        self,
        config_provider: Callable[[], Config],
        backend_factory: Callable[[str], AiBackend] = AnthropicBackend,
        key_loader: Callable[[], str | None] = load_key,
        ledger_path: Path = LEDGER_PATH,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._backend_factory = backend_factory
        self._key_loader = key_loader
        self._ledger_path = ledger_path
        self._now = now
        self._busy = False
        self._has_key: bool | None = None  # cached for available(); submit() reads the key again
        self._key_rejected = False  # the API refused the key: hide AI until it changes or a request succeeds

    @property
    def busy(self) -> bool:
        return self._busy

    def month_totals(self) -> Totals:
        return totals(read_entries(self._ledger_path), self._now())

    def available(self) -> bool:
        """AI is on, a key is saved and the API has not rejected it: AI links and the AI shortcut work.

        The key check is cached so this can run on every card refresh without reading Credential
        Manager; a key deleted outside Proofline keeps it True until the next Save or Remove, which
        is harmless because submit() loads the key again before sending.
        """
        if not self._config_provider().ai_enabled or self._key_rejected:
            return False
        if self._has_key is None:
            try:
                self._has_key = bool(self._key_loader())
            except Exception:  # an unreadable key store means no usable key
                log.warning("Could not read the API key from Credential Manager", exc_info=True)
                self._has_key = False
        return self._has_key

    def key_changed(self) -> None:
        """The key was saved or removed: read it again on the next available()."""
        self._has_key = None
        self._key_rejected = False

    def refusal_reason(self, request: AiRequest) -> str | None:
        """The message request would be refused with, or None when it can be sent."""
        refusal = self._refusal(request)
        return refusal[0] if refusal else None

    def _refusal(self, request: AiRequest) -> tuple[str, str] | None:
        """(message, kind) when request cannot be sent; kinds: off, no_key, too_long, busy, cap."""
        config = self._config_provider()
        if not config.ai_enabled:
            return OFF_MESSAGE, "off"
        if not self._key_loader():
            return NO_KEY_MESSAGE, "no_key"
        if len(request.text) > MAX_INPUT_CHARS:
            return TOO_LONG_MESSAGE, "too_long"
        if self._busy:
            return BUSY_MESSAGE, "busy"
        cap = config.ai_monthly_cap_cents / CENTS_PER_DOLLAR
        if not can_spend(self.month_totals().month, cap, _worst_case(request, config.ai_model)):
            return CAP_MESSAGE, "cap"
        return None

    def submit(self, request: AiRequest) -> bool:
        """Send request in the background; False (and failed emitted) when it is refused."""
        refusal = self._refusal(request)
        key = self._key_loader() if refusal is None else None
        if refusal is not None or key is None:
            message, kind = refusal or (NO_KEY_MESSAGE, "no_key")
            log.info("AI request refused (%s, %s)", request.job, kind)
            self.failed.emit(request, message, kind)
            return False
        model = self._config_provider().ai_model
        self._busy = True
        log.info("AI request (%s, %s, %d characters)", request.job, model, len(request.text))
        run_in_background(
            lambda: self._backend_factory(key).send(request, model),
            lambda result: self._on_done(request, model, result),
            lambda exc: self._on_error(request, model, exc),
        )
        return True

    def _on_done(self, request: AiRequest, model: str, result: AiResult) -> None:
        self._busy = False
        self._key_rejected = False
        self._record(request, model, result.input_tokens, result.output_tokens, estimated=False)
        self.finished.emit(request, result)

    def _on_error(self, request: AiRequest, model: str, exc: Exception) -> None:
        self._busy = False
        if isinstance(exc, AiError) and exc.input_tokens is not None:
            self._record(request, model, exc.input_tokens, exc.output_tokens or 0, estimated=False)
        elif not isinstance(exc, AiError) or exc.kind in UNKNOWN_OUTCOME_KINDS:
            self._record(request, model, estimate_input_tokens(request.text), request.max_tokens, estimated=True)
        kind = exc.kind if isinstance(exc, AiError) else "error"
        if kind == "auth":
            self._key_rejected = True
        log.warning("AI request failed (%s, %s)", request.job, exc.kind if isinstance(exc, AiError) else type(exc).__name__)
        self.failed.emit(request, exc.message if isinstance(exc, AiError) else FAILED_MESSAGE, kind)

    def _record(self, request: AiRequest, model: str, input_tokens: int, output_tokens: int, estimated: bool) -> None:
        entry = UsageEntry(self._now(), request.job, model, input_tokens, output_tokens,
                           cost(model, input_tokens, output_tokens), estimated)
        try:
            record(entry, self._ledger_path)
        except OSError as exc:
            log.warning("Could not record AI usage (%s)", exc)


def _worst_case(request: AiRequest, model: str) -> float:
    return cost(model, estimate_input_tokens(request.text), request.max_tokens)
