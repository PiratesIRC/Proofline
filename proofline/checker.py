"""Sends paused text to LanguageTool in the background and reports the results."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from proofline.config import Config
from proofline.hidden_chars import hidden_matches, merge_matches
from proofline.logging_setup import text_logging_enabled
from proofline.lt_client import ERROR_TIMEOUT, LanguageToolClient, Match
from proofline.text_snapshot import FieldSnapshot
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

MS_PER_S = 1000
MAX_ATTEMPTS = 3  # a check is reported failed only after this many tries in a row fail
RETRY_DELAY_MS = 1000  # pause before trying a failed check again
CACHE_SIZE = 32  # most recent (settings, text) results kept; refocusing an unchanged field reuses one

ClientFactory = Callable[[Config], LanguageToolClient]
CacheKey = tuple


def cache_key(config: Config, text: str) -> CacheKey:
    """The settings that change what LanguageTool reports, plus the text checked."""
    return (
        config.server_url,
        config.language,
        tuple(config.disabled_rules),
        tuple(config.disabled_categories),
        config.picky,
        config.flag_hidden_characters,
        text,
    )


def client_for(config: Config) -> LanguageToolClient:
    return LanguageToolClient(
        config.server_url,
        config.language,
        disabled_rules=config.disabled_rules,
        disabled_categories=config.disabled_categories,
        picky=config.picky,
    )


class GrammarChecker(QObject):
    """checked(FieldSnapshot, tuple[Match, ...]) or failed(str) follows each check().

    Only the latest request is reported; results of superseded checks are dropped. A failed
    request is tried again quietly, so a single slow or dropped reply does not show an error.
    A timeout is reported at once: the server already had its full wait. Successful results are
    kept in a small LRU cache, so a check of unchanged text with the same settings sends no request.
    """

    checked = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        config_provider: Callable[[], Config],
        client_factory: ClientFactory = client_for,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._client_factory = client_factory
        self._generation = 0
        self._cache: OrderedDict[CacheKey, tuple[Match, ...]] = OrderedDict()

    def check(self, snapshot: FieldSnapshot) -> None:
        self._generation += 1
        generation = self._generation
        key = cache_key(self._config_provider(), snapshot.text)
        if key in self._cache:
            self._cache.move_to_end(key)
            matches = self._cache[key]
            started = time.monotonic()
            # Delivered on the event loop like a network result, so callers see the same ordering.
            QTimer.singleShot(0, lambda: self._on_done(generation, snapshot, matches, started, None))
            return
        self._attempt(generation, snapshot, 1)

    def _attempt(self, generation: int, snapshot: FieldSnapshot, attempt: int) -> None:
        if generation != self._generation:
            return  # a newer check replaced this one while it waited to retry
        config = self._config_provider()
        # A fresh client per check: requests.Session is not guaranteed thread-safe.
        client = self._client_factory(config)
        started = time.monotonic()
        flag_hidden = config.flag_hidden_characters
        key = cache_key(config, snapshot.text)

        def run() -> tuple[Match, ...]:
            matches = client.check(snapshot.text)
            return merge_matches(matches, hidden_matches(snapshot.text)) if flag_hidden else matches

        run_in_background(
            run,
            lambda matches: self._on_done(generation, snapshot, matches, started, key),
            lambda exc: self._on_failed(generation, snapshot, attempt, exc),
        )

    def _on_done(
        self,
        generation: int,
        snapshot: FieldSnapshot,
        matches: tuple[Match, ...],
        started: float,
        key: CacheKey | None,
    ) -> None:
        if key is not None:
            self._remember(key, matches)
        if generation != self._generation:
            log.debug("Dropping result of a superseded check")
            return
        elapsed_ms = (time.monotonic() - started) * MS_PER_S
        log.info("%d issue(s) in %.0f ms for %s", len(matches), elapsed_ms, snapshot.describe())
        for match in matches:
            if text_logging_enabled():
                log.debug("  %r -> %s [%s]", match.error_text, list(match.replacements), match.rule_id)
            else:
                log.debug("  %s at %d+%d", match.rule_id, match.offset, match.length)
        self.checked.emit(snapshot, matches)

    def _remember(self, key: CacheKey, matches: tuple[Match, ...]) -> None:
        self._cache[key] = matches
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    def _on_failed(self, generation: int, snapshot: FieldSnapshot, attempt: int, exc: Exception) -> None:
        if generation != self._generation:
            return
        if _is_timeout(exc):
            log.warning("Check timed out, not retried: %s", exc)
            self.failed.emit(str(exc))
            return
        if attempt < MAX_ATTEMPTS:
            log.info("Check attempt %d of %d failed, trying again: %s", attempt, MAX_ATTEMPTS, exc)
            QTimer.singleShot(RETRY_DELAY_MS, lambda: self._attempt(generation, snapshot, attempt + 1))
            return
        log.warning("Check failed: %s", exc)
        self.failed.emit(str(exc))


def _is_timeout(exc: Exception) -> bool:
    return getattr(exc, "kind", None) == ERROR_TIMEOUT
