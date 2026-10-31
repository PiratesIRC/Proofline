"""Anonymous usage counts for the README badges: Corrections Applied, AI Rephrases, Active Installs.

Works like the PiratesIRC Dispatcharr plugins. usage_client.py (vendored, never
edited) sends the total from the ledger plus a random id for this install to the
plugin-stats Worker, at most once an hour (ten minutes after new work), and only
while Settings › Advanced › Share anonymous usage counts is on. Turning it off makes
the next report ask the server to delete this install's figures.

The ledger gets one line per correction actually applied. Checks, ignored issues and
corrections that fail verification are not counted. AI Rephrases is a second count under its
own Worker key (the Worker allows one counter per key), with its own ledger and install id: one
line per AI change actually pasted (a Rephrase rewording, or any fix built from an AI finding:
Find more, Rewrite for clarity, Change tone, Accept all). No text is ever sent.
"""

from __future__ import annotations

import glob
import json
import logging
import msvcrt
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer

from proofline.config import APP_DATA_DIR, Config
from proofline.usage_client import SETTING_ID, UsageReporter, jsonl_sum

log = logging.getLogger(__name__)

PLUGIN = "proofline"  # the Worker allowlist key and badge slug
COUNTER = "corrections_applied"
LABEL = "Corrections Applied"
LEDGER_PATH = APP_DATA_DIR / "usage_counts.jsonl"
AI_PLUGIN = "proofline-ai"  # a second Worker allowlist key: one counter per key
AI_COUNTER = "ai_rephrases"
AI_LABEL = "AI Rephrases"
AI_LEDGER_PATH = APP_DATA_DIR / "usage_ai_rephrases.jsonl"
USAGE_DIR = APP_DATA_DIR / "usage"  # the client keeps its id and timing files under <dir>/proofline
REPORT_TICK_MS = 60 * 60 * 1000  # the client itself holds sends to once an hour


def windows_lock(fd: int) -> bool:
    """Non-blocking exclusive lock for the client (it uses fcntl, which Windows lacks).

    Released when the client closes fd after its send.
    """
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def ledger_total(path: Path = LEDGER_PATH, counter: str = COUNTER) -> int:
    return jsonl_sum(glob.escape(str(path)), key=counter, logger=log)


def make_reporter(
    settings_fn: Callable[[], dict], ledger: Path = LEDGER_PATH, data_dir: Path = USAGE_DIR, **client_options: object,
) -> UsageReporter:
    return UsageReporter(
        plugin=PLUGIN, counter=COUNTER, label=LABEL, total_fn=lambda: ledger_total(ledger),
        settings_fn=settings_fn, data_dir=str(data_dir), lock=windows_lock, **client_options,
    )


def make_ai_reporter(
    settings_fn: Callable[[], dict], ledger: Path = AI_LEDGER_PATH, data_dir: Path = USAGE_DIR,
    **client_options: object,
) -> UsageReporter:
    return UsageReporter(
        plugin=AI_PLUGIN, counter=AI_COUNTER, label=AI_LABEL, total_fn=lambda: ledger_total(ledger, AI_COUNTER),
        settings_fn=settings_fn, data_dir=str(data_dir), lock=windows_lock, **client_options,
    )


def usage_settings(config: Config) -> dict:
    """The settings dict the client reads its consent from."""
    return {SETTING_ID: config.share_usage_counts}


def record_correction(path: Path = LEDGER_PATH) -> bool:
    """Append one applied correction to the ledger; False (logged) if it can't be written."""
    return _record(path, COUNTER)


def record_ai_rephrase(path: Path = AI_LEDGER_PATH) -> bool:
    """Append one applied AI rewording to its ledger; False (logged) if it can't be written."""
    return _record(path, AI_COUNTER)


def _record(path: Path, counter: str) -> bool:
    line = json.dumps({counter: 1, "ts": datetime.now(UTC).isoformat(timespec="seconds")})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        log.warning("Could not record the correction for the usage count: %s", exc)
        return False
    return True


class UsageReporting(QObject):
    """Reports at start, hourly, after each recorded correction and when the setting changes.

    Every call returns at once (the client sends on its own thread) and never raises.
    """

    def __init__(
        self, config_provider: Callable[[], Config], reporter: UsageReporter | None = None,
        record: Callable[[], bool] = record_correction, tick_ms: int = REPORT_TICK_MS,
        ai_reporter: UsageReporter | None = None, record_ai: Callable[[], bool] = record_ai_rephrase,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._reporter = reporter or make_reporter(lambda: usage_settings(config_provider()))
        self._ai_reporter = ai_reporter or make_ai_reporter(lambda: usage_settings(config_provider()))
        self._record = record
        self._record_ai = record_ai
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.report)

    def start(self) -> None:
        self._timer.start()
        self.report()

    def stop(self) -> None:
        self._timer.stop()

    def report(self, force: bool = False) -> None:
        for reporter in (self._reporter, self._ai_reporter):
            self._send(reporter, force)

    def _send(self, reporter: UsageReporter, force: bool = False) -> None:
        try:
            reporter.report(usage_settings(self._config_provider()), log, force=force)
        except Exception:
            log.debug("Usage report skipped", exc_info=True)

    def on_correction_applied(self) -> None:
        if self._record():
            self._send(self._reporter, force=True)

    def on_ai_rephrase_applied(self) -> None:
        if self._record_ai():
            self._send(self._ai_reporter, force=True)

    def on_setting_changed(self) -> None:
        """Turning sharing off sends the delete request now rather than within the hour."""
        self.report()
