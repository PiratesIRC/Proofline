"""Sends AI requests to the selected provider, one at a time, within the monthly spending limit,
and records their cost.

Runs on the GUI thread; the HTTP call itself goes to the Qt thread pool. Every request is
checked first: AI turned on, a key saved when the provider needs one, the text short enough,
no other request running, prices known (OpenRouter), and this month's recorded cost plus the
request's worst case within the limit. Unpriced providers (Ollama, Other) skip the price table
and the limit entirely; their entries are logged with cost 0 and cost_known False.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from proofline.ai_backends import make_backend
from proofline.ai_client import (
    MAX_INPUT_CHARS,
    AiBackend,
    AiError,
    AiRequest,
    AiResult,
)
from proofline.ai_keys import load_provider_key
from proofline.ai_prices import (
    ModelPrice,
    cost,
    dearest,
    estimate_input_tokens,
    most_expensive,
    price_for,
)
from proofline.ai_providers import ProviderSpec, provider
from proofline.ai_usage import (
    LEDGER_PATH,
    TokenTotals,
    Totals,
    UsageEntry,
    can_spend,
    read_entries,
    record,
    totals,
)
from proofline.ai_usage import token_totals as usage_token_totals
from proofline.config import OTHER_ID, Config, is_insecure_remote
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

OFF_MESSAGE = "AI is turned off in Settings."
NO_KEY_MESSAGE = "Add an API key in Settings, AI."
BUSY_MESSAGE = "Another AI request is still running."
TOO_LONG_MESSAGE = "Select a shorter part (at most 8,000 characters)."
CAP_MESSAGE = "Monthly AI limit reached."
NO_MODEL_MESSAGE = "Choose a model in Settings, AI."
NO_PRICES_MESSAGE = "Press Refresh to load OpenRouter's prices first."
NO_PRICE_MESSAGE = "This model's price is unknown, so the spending limit cannot be checked."
LOG_UNREADABLE_MESSAGE = "Proofline could not read its AI usage log, so the spending limit cannot be checked."
FAILED_MESSAGE = "The AI request failed."
# sent, maybe billed, no token counts back (a bad_response without counts is billed the same way)
UNKNOWN_OUTCOME_KINDS = ("timeout", "network", "server", "bad_response")
CENTS_PER_DOLLAR = 100
OPENROUTER_ID = "openrouter"  # its price list is fetched at runtime (set_live_prices)
REPORTED_COST_FACTOR = 10  # a reported cost above this many times the worst case at list price is not believed


class AiService(QObject):
    finished = pyqtSignal(object, object)  # AiRequest, AiResult
    failed = pyqtSignal(object, str, str)  # AiRequest, one-line message for the user, kind (see _refusal)

    def __init__(
        self,
        config_provider: Callable[[], Config],
        backend_factory: Callable[[ProviderSpec, str | None, str], AiBackend] = make_backend,
        key_loader: Callable[[str], str | None] = load_provider_key,
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
        self._has_key: dict[str, bool] = {}  # per provider id, cached for available()
        self._key_rejected: dict[str, bool] = {}  # per provider id: the API refused its key
        self._live_prices: dict[str, tuple[ModelPrice, ...]] = {}
        self._unrecorded: list[UsageEntry] = []  # entries the log could not be written with, this session only
        self._unreadable_logged = False  # the unreadable-log warning is written once per session

    @property
    def busy(self) -> bool:
        return self._busy

    def provider(self) -> ProviderSpec:
        """The provider chosen in Settings."""
        return provider(self._config_provider().ai_provider)

    def month_totals(self) -> Totals:
        """Shown in Settings: an unreadable log counts only this session's requests."""
        return totals(self._shown_entries(), self._now())

    def token_totals(self, pid: str) -> TokenTotals:
        """This month's token counts for provider pid (an unreadable log counts only this session)."""
        return usage_token_totals(self._shown_entries(), self._now(), pid)

    def _shown_entries(self) -> list[UsageEntry]:
        entries = self._ledger_entries()
        return self._unrecorded if entries is None else entries

    def _ledger_entries(self) -> list[UsageEntry] | None:
        """The saved ledger plus the entries this session could not write; None when the saved log
        cannot be read (the limit then fails closed for priced providers)."""
        try:
            saved = read_entries(self._ledger_path)
        except OSError as exc:
            if not self._unreadable_logged:
                self._unreadable_logged = True
                log.warning("Could not read the AI usage log (%s)", exc)
            return None
        return saved + self._unrecorded

    def _limit_spend(self) -> float | None:
        """This month's recorded dollars for the limit check; None when the saved log cannot be read."""
        entries = self._ledger_entries()
        return None if entries is None else totals(entries, self._now()).month

    def available(self) -> bool:
        """AI is on, the selected provider's key is saved (when it needs one) and that provider's
        API has not rejected the key: AI links and the AI shortcut work.

        The key check is cached so this can run on every card refresh without reading Credential
        Manager; a key deleted outside Proofline keeps it True until the next Save or Remove, which
        is harmless because submit() loads the key again before sending.
        """
        config = self._config_provider()
        if not config.ai_enabled:
            return False
        spec = provider(config.ai_provider)
        if self._key_rejected.get(spec.id):
            return False
        if spec.id == OPENROUTER_ID and not self._live_prices.get(spec.id):  # no prices, no spending check
            return False
        return spec.key != "required" or self._has_saved_key(spec.id)

    def _has_saved_key(self, pid: str) -> bool:
        if pid not in self._has_key:
            try:
                self._has_key[pid] = bool(self._key_loader(pid))
            except Exception:  # an unreadable key store means no usable key
                log.warning("Could not read the API key from Credential Manager", exc_info=True)
                self._has_key[pid] = False
        return self._has_key[pid]

    def key_changed(self, pid: str | None = None) -> None:
        """A key was saved, or removed: read it again on the next available(). None (the Settings page does not
        say which provider) does this for every provider."""
        if pid is None:
            self._has_key.clear()
            self._key_rejected.clear()
        else:
            self._has_key.pop(pid, None)
            self._key_rejected.pop(pid, None)

    def set_live_prices(self, pid: str, prices: tuple[ModelPrice, ...]) -> None:
        """The prices fetched at runtime for provider pid; replaces any earlier list."""
        self._live_prices[pid] = tuple(prices)

    def price(self, spec: ProviderSpec, model: str) -> ModelPrice | None:
        """The price charged for model: its price table row, else its live row, else the provider's
        most expensive priced model (a typed or new name), else for OpenRouter its most expensive
        live row. None means unpriced."""
        if not spec.priced:  # Ollama and Other: never touch the price table
            return None
        live = self._live_prices.get(spec.id, ())
        row = price_for(spec.id, model) or next((m for m in live if m.model_id == model), None)
        if row is not None:
            return row
        if spec.id == OPENROUTER_ID:  # no fixed table: its live list, or nothing until Refresh
            return dearest(live)
        return most_expensive(spec.id)

    def refusal_reason(self, request: AiRequest) -> str | None:
        """The message request would be refused with, or None when it can be sent."""
        config = self._config_provider()
        spec = provider(config.ai_provider)
        refusal = self._refusal(request, config, spec, self._key_for_send(spec, config))
        return refusal[0] if refusal else None

    def _refusal(self, request: AiRequest, config: Config, spec: ProviderSpec,
                 key: str | None) -> tuple[str, str] | None:
        """(message, kind) when request cannot be sent; kinds: off, no_key, no_model, too_long, busy,
        no_prices, no_price, log_unreadable, cap."""
        if not config.ai_enabled:
            return OFF_MESSAGE, "off"
        if spec.key == "required" and not key:
            return NO_KEY_MESSAGE, "no_key"
        model = config.ai_model_for(spec.id)
        if not model:  # OpenRouter, Ollama and Other have no default model
            return NO_MODEL_MESSAGE, "no_model"
        if len(request.text) > MAX_INPUT_CHARS:
            return TOO_LONG_MESSAGE, "too_long"
        if self._busy:
            return BUSY_MESSAGE, "busy"
        price = self.price(spec, model)
        if price is None and spec.id == OPENROUTER_ID:
            return NO_PRICES_MESSAGE, "no_prices"
        if price is None and spec.priced:  # a priced provider must never skip the limit
            return NO_PRICE_MESSAGE, "no_price"
        if price is not None:
            spent = self._limit_spend()
            if spent is None:  # unknown spending: a priced request is not sent
                return LOG_UNREADABLE_MESSAGE, "log_unreadable"
            cap = config.ai_monthly_cap_cents / CENTS_PER_DOLLAR
            if not can_spend(spent, cap, _worst_case(request, price)):
                return CAP_MESSAGE, "cap"
        return None

    def _key_for_send(self, spec: ProviderSpec, config: Config) -> str | None:
        """The key to send with, read now (never from the cache). Only the selected provider's key
        is read, and only when AI is on and the provider takes a key. Other's key is not sent when its
        address is plain http to another computer, or when it was saved for a different address."""
        if not config.ai_enabled or spec.key == "none":
            return None
        if spec.id == OTHER_ID and (is_insecure_remote(config.ai_address_for(spec.id))
                                    or not config.other_key_applies()):
            return None
        return self._key_loader(spec.id)

    def submit(self, request: AiRequest) -> bool:
        """Send request in the background; False (and failed emitted) when it is refused."""
        config = self._config_provider()
        spec = provider(config.ai_provider)
        key = self._key_for_send(spec, config)
        refusal = self._refusal(request, config, spec, key)
        if refusal is not None:
            message, kind = refusal
            log.info("AI request refused (%s, %s)", request.job, kind)
            self.failed.emit(request, message, kind)
            return False
        model = config.ai_model_for(spec.id)
        address = config.ai_address_for(spec.id)
        self._busy = True
        log.info("AI request (%s, %s, %s, %d characters)", request.job, spec.id, model, len(request.text))
        self._send(_Attempt(spec, request, model, key, address, self.price(spec, model)))
        return True

    def _send(self, attempt: _Attempt) -> None:
        """Run one attempt in the background; its outcome comes back on the GUI thread."""
        def call() -> AiResult:
            backend = self._backend_factory(attempt.spec, attempt.key, attempt.address)
            return backend.send(attempt.request, attempt.model)

        run_in_background(call, lambda result: self._on_done(attempt, result),
                          lambda exc: self._on_error(attempt, exc))

    def _on_done(self, attempt: _Attempt, result: AiResult) -> None:
        self._busy = False
        self._key_rejected.pop(attempt.spec.id, None)
        self._record(attempt, result.input_tokens, result.output_tokens, estimated=False, reported=result.cost)
        self.finished.emit(attempt.request, result)

    def _on_error(self, attempt: _Attempt, exc: Exception) -> None:
        self._busy = False  # cleared first, so nothing below can leave the service stuck busy
        try:
            self._record_error(attempt, exc)
            retry = self._retry_allowed(attempt, exc)
        except Exception:  # noqa: BLE001 - the decision must not swallow the outcome: report the original failure
            log.warning("Could not decide on a retry; the original failure is reported")
            retry = False
        if retry:
            self._busy = True  # set again only because attempt 2 is really sent
            log.info("AI retry (%s, %s)", attempt.request.job, attempt.spec.id)
            self._send(replace(attempt, number=attempt.number + 1))
            return
        self._report_failure(attempt, exc)

    def _report_failure(self, attempt: _Attempt, exc: Exception) -> None:
        spec, request = attempt.spec, attempt.request
        kind = exc.kind if isinstance(exc, AiError) else "error"
        if kind == "auth":
            self._key_rejected[spec.id] = True
        log.warning("AI request failed (%s, %s, %s)", request.job, spec.id,
                    exc.kind if isinstance(exc, AiError) else type(exc).__name__)
        self.failed.emit(request, exc.message if isinstance(exc, AiError) else FAILED_MESSAGE, kind)

    def _record_error(self, attempt: _Attempt, exc: Exception) -> None:
        """Record what a failed attempt cost: its reported tokens, else the worst case when the outcome is unknown."""
        request = attempt.request
        if isinstance(exc, AiError) and exc.input_tokens is not None:
            self._record(attempt, exc.input_tokens, exc.output_tokens or 0, estimated=False)
        elif not isinstance(exc, AiError) or exc.kind in UNKNOWN_OUTCOME_KINDS:
            self._record(attempt, estimate_input_tokens(request.text), request.max_tokens, estimated=True)

    def _retry_allowed(self, attempt: _Attempt, exc: Exception) -> bool:
        """True for one DeepSeek retry: a non-matching JSON answer on the first attempt, when the second
        attempt's worst case still fits the limit with the first attempt already recorded."""
        spec = attempt.spec
        if attempt.number != 1 or spec.json_mode != "object" or not isinstance(exc, AiError):
            return False
        if exc.kind != "bad_response" or exc.cut_off:  # a cut-off answer would come back the same way
            return False
        config = self._config_provider()
        if not config.ai_enabled or self.provider().id != spec.id:  # turned off or switched since attempt 1
            return False
        price = attempt.price
        if price is None:
            return False
        spent = self._limit_spend()
        if spent is None:  # unreadable log: the limit cannot be checked, so no retry
            return False
        cap = config.ai_monthly_cap_cents / CENTS_PER_DOLLAR
        return can_spend(spent, cap, _worst_case(attempt.request, price))

    def _record(self, attempt: _Attempt, input_tokens: int, output_tokens: int, estimated: bool,
                reported: float | None = None) -> None:
        dollars, known = self._dollars(attempt, input_tokens, output_tokens, reported)
        entry = UsageEntry(self._now(), attempt.request.job, attempt.model, input_tokens, output_tokens, dollars,
                           estimated, provider=attempt.spec.id, cost_known=known)
        try:
            record(entry, self._ledger_path)
        except OSError as exc:
            self._unrecorded.append(entry)
            log.warning("Could not record AI usage (%s); this session's spending still counts", exc)

    def _dollars(self, attempt: _Attempt, input_tokens: int, output_tokens: int,
                 reported: float | None) -> tuple[float, bool]:
        """(dollars, cost known): the cost the backend reported, else the price the request was sent at, else
        0 and unknown. The price was resolved at submit, so a price list refreshed in flight does not change it."""
        if reported is not None and _trusted_cost(attempt, reported):
            return reported, True
        if reported is not None and _trusted_shape(attempt.spec, reported):
            log.warning("OpenRouter reported a cost far above the list price; the list price is recorded instead")
        if attempt.price is None:
            return 0.0, False
        return cost(attempt.price, input_tokens, output_tokens), True


@dataclass(frozen=True)
class _Attempt:
    """One send of a request, with what it is sent with; number is 1 for the first send, 2 for a retry."""

    spec: ProviderSpec
    request: AiRequest
    model: str
    key: str | None
    address: str
    price: ModelPrice | None  # resolved when the request was sent: what it is charged at
    number: int = 1


def _trusted_shape(spec: ProviderSpec, reported: float) -> bool:
    """Only OpenRouter's reported cost is used; it must be a finite, non-negative number."""
    return spec.id == OPENROUTER_ID and math.isfinite(reported) and reported >= 0


def _trusted_cost(attempt: _Attempt, reported: float) -> bool:
    """A reported cost is used only when its shape is right and it is at most REPORTED_COST_FACTOR times the
    worst case at the list price the request was sent at (an unknown list price trusts nothing)."""
    if not _trusted_shape(attempt.spec, reported) or attempt.price is None:
        return False
    return reported <= REPORTED_COST_FACTOR * _worst_case(attempt.request, attempt.price)


def _worst_case(request: AiRequest, price: ModelPrice) -> float:
    return cost(price, estimate_input_tokens(request.text), request.max_tokens)
