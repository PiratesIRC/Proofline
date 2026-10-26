"""Sends paused text to LanguageTool in the background and reports the results."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from proofline.config import Config
from proofline.hidden_chars import hidden_matches, merge_matches
from proofline.logging_setup import text_logging_enabled
from proofline.lt_client import LanguageToolClient, Match
from proofline.text_snapshot import FieldSnapshot
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

MS_PER_S = 1000

ClientFactory = Callable[[Config], LanguageToolClient]


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

    Only the latest request is reported; results of superseded checks are dropped.
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

    def check(self, snapshot: FieldSnapshot) -> None:
        config = self._config_provider()
        # A fresh client per check: requests.Session is not guaranteed thread-safe.
        client = self._client_factory(config)
        self._generation += 1
        generation = self._generation
        started = time.monotonic()
        flag_hidden = config.flag_hidden_characters

        def run() -> tuple[Match, ...]:
            matches = client.check(snapshot.text)
            return merge_matches(matches, hidden_matches(snapshot.text)) if flag_hidden else matches

        run_in_background(
            run,
            lambda matches: self._on_done(generation, snapshot, matches, started),
            lambda exc: self._on_failed(generation, exc),
        )

    def _on_done(
        self,
        generation: int,
        snapshot: FieldSnapshot,
        matches: tuple[Match, ...],
        started: float,
    ) -> None:
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

    def _on_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._generation:
            return
        log.warning("Check failed: %s", exc)
        self.failed.emit(str(exc))
