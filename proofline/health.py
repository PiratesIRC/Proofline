"""Tracks whether the LanguageTool server is reachable and retries while it is not."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from proofline.checker import client_for
from proofline.config import Config, redact_url
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

RETRY_MS = 60_000
PROBE_TEXT = "This is a test."
NOTICE_MIN_GAP_S = 30 * 60

ClientFactory = Callable[[Config], object]


class ServerHealth(QObject):
    """healthy() or unhealthy(str) follows each probe or reported grammar check.

    While unhealthy, a probe is retried every retry_ms until the server answers.
    Results of superseded probes are dropped.
    """

    healthy = pyqtSignal()
    unhealthy = pyqtSignal(str)

    def __init__(
        self,
        config_provider: Callable[[], Config],
        client_factory: ClientFactory = client_for,
        retry_ms: int = RETRY_MS,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._client_factory = client_factory
        self._generation = 0
        self._is_healthy: bool | None = None
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(retry_ms)
        self._retry_timer.timeout.connect(self.check_now)

    @property
    def is_healthy(self) -> bool | None:
        """None until the first result, then True or False."""
        return self._is_healthy

    def check_now(self) -> None:
        """Send a short probe text to the server in the background."""
        config = self._config_provider()
        client = self._client_factory(config)
        self._generation += 1
        generation = self._generation
        run_in_background(
            lambda: client.check(PROBE_TEXT),
            lambda _matches: self._on_probe_done(generation),
            lambda exc: self._on_probe_failed(generation, config, exc),
        )

    def report_success(self) -> None:
        """Called after a normal grammar check succeeds."""
        was_unhealthy = self._is_healthy is False
        self._mark_healthy()
        if was_unhealthy:
            self.healthy.emit()

    def report_failure(self, message: str) -> None:
        """Called after a normal grammar check fails."""
        self._mark_unhealthy(message)
        self._schedule_retry()

    def _on_probe_done(self, generation: int) -> None:
        if generation != self._generation:
            log.debug("Dropping result of a superseded health check")
            return
        self._mark_healthy()
        self.healthy.emit()

    def _on_probe_failed(self, generation: int, config: Config, exc: Exception) -> None:
        if generation != self._generation:
            return
        log.warning("LanguageTool server at %s is unreachable: %s", redact_url(config.server_url), exc)
        self._mark_unhealthy(str(exc))
        self._schedule_retry()

    def _mark_healthy(self) -> None:
        self._is_healthy = True
        self._retry_timer.stop()

    def _mark_unhealthy(self, message: str) -> None:
        self._is_healthy = False
        self.unhealthy.emit(message)

    def _schedule_retry(self) -> None:
        if not self._retry_timer.isActive():
            self._retry_timer.start()


class OutageNotices:
    """Decides when 'can't reach the server' deserves a notification.

    One notification per outage, whatever its error text, and at most one per min_gap_s,
    so a server that keeps dropping out doesn't notify on every drop. The tray icon shows
    the live state in between.
    """

    def __init__(self, min_gap_s: float = NOTICE_MIN_GAP_S, clock: Callable[[], float] = time.monotonic) -> None:
        self._min_gap_s = min_gap_s
        self._clock = clock
        self._in_outage = False
        self._last_notice: float | None = None

    def should_notify(self) -> bool:
        """Call on every failure; True only for the first failure of an outage outside the gap."""
        if self._in_outage:
            return False
        self._in_outage = True
        now = self._clock()
        if self._last_notice is not None and now - self._last_notice < self._min_gap_s:
            log.info("Server unreachable again; notification skipped (last one %.0f s ago)", now - self._last_notice)
            return False
        self._last_notice = now
        return True

    def recovered(self) -> None:
        self._in_outage = False
