"""Tests for server health probing and the tray error state."""

from __future__ import annotations

import threading

from PyQt6.QtGui import QIcon

from proofline.config import Config
from proofline.health import PROBE_TEXT, ServerHealth
from proofline.lt_client import LanguageToolError
from proofline.tray import (
    ACTIVE_COLOR,
    ERROR_COLOR,
    ICON_SIZE,
    PAUSED_COLOR,
    TrayIcon,
    make_icon,
)

SHORT_RETRY_MS = 50
WAIT_MS = 2000
# Inside the circle, above the centred "P" or "!" glyph.
SAMPLE_X = 32
SAMPLE_Y = 8
ERROR_TOOLTIP_PREFIX = "Proofline: can't reach the server\n"
LONG_MESSAGE_CHARS = 200
TOOLTIP_MESSAGE_CHARS = 120


class FakeClient:
    def __init__(self, error: Exception | None) -> None:
        self._error = error

    def check(self, text: str) -> tuple[()]:
        assert text == PROBE_TEXT
        if self._error is not None:
            raise self._error
        return ()


class FakeFactory:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    def __call__(self, config: Config) -> FakeClient:
        self.calls += 1
        return FakeClient(self.error)


def _health(factory: FakeFactory, retry_ms: int = SHORT_RETRY_MS) -> ServerHealth:
    return ServerHealth(lambda: Config(), client_factory=factory, retry_ms=retry_ms)


def test_probe_success_emits_healthy(qtbot):
    factory = FakeFactory()
    health = _health(factory)
    assert health.is_healthy is None
    with qtbot.waitSignal(health.healthy, timeout=WAIT_MS):
        health.check_now()
    assert health.is_healthy is True
    assert factory.calls == 1


def test_probe_failure_emits_unhealthy_and_retries(qtbot):
    factory = FakeFactory()
    factory.error = LanguageToolError("server down")
    health = _health(factory)
    with qtbot.waitSignal(health.unhealthy, timeout=WAIT_MS) as blocker:
        health.check_now()
    assert blocker.args == ["server down"]
    assert health.is_healthy is False

    factory.error = None
    with qtbot.waitSignal(health.healthy, timeout=WAIT_MS):
        pass
    assert factory.calls >= 2
    assert health.is_healthy is True


def test_superseded_probe_result_is_ignored(qtbot):
    gate = threading.Event()
    finished = threading.Event()

    class SlowClient:
        def check(self, text: str) -> tuple[()]:
            gate.wait(WAIT_MS / 1000)
            finished.set()
            raise LanguageToolError("stale failure")

    clients = [SlowClient(), FakeClient(None)]
    health = ServerHealth(lambda: Config(), client_factory=lambda _c: clients.pop(0), retry_ms=SHORT_RETRY_MS)
    with qtbot.assertNotEmitted(health.unhealthy, wait=0):
        health.check_now()
        with qtbot.waitSignal(health.healthy, timeout=WAIT_MS):
            health.check_now()
        gate.set()
        qtbot.waitUntil(finished.is_set, timeout=WAIT_MS)
        qtbot.wait(20)
    assert health.is_healthy is True


def test_report_failure_emits_and_schedules_retry(qtbot):
    factory = FakeFactory()
    health = _health(factory)
    with qtbot.waitSignal(health.unhealthy, timeout=WAIT_MS) as blocker:
        health.report_failure("grammar failed")
    assert blocker.args == ["grammar failed"]
    assert health.is_healthy is False
    qtbot.waitUntil(lambda: factory.calls >= 1, timeout=WAIT_MS)


def test_report_success_recovers_only_when_unhealthy(qtbot):
    factory = FakeFactory()
    health = _health(factory, retry_ms=60_000)
    with qtbot.assertNotEmitted(health.healthy, wait=0):
        health.report_success()
    assert health.is_healthy is True

    health.report_failure("down")
    with qtbot.waitSignal(health.healthy, timeout=WAIT_MS):
        health.report_success()
    assert health.is_healthy is True
    assert factory.calls == 0


def test_make_icon_background_is_transparent(qtbot):
    image = make_icon(ACTIVE_COLOR).pixmap(ICON_SIZE, ICON_SIZE).toImage()
    assert image.pixelColor(0, 0).alpha() == 0


def _centre_colour(icon: QIcon) -> str:
    image = icon.pixmap(ICON_SIZE, ICON_SIZE).toImage()
    return image.pixelColor(SAMPLE_X, SAMPLE_Y).name()


def test_set_error_swaps_icon_and_tooltip(qtbot):
    tray = TrayIcon(enabled=True)
    assert tray.has_error is False
    assert _centre_colour(tray.icon()) == ACTIVE_COLOR

    tray.set_error("boom")
    assert tray.has_error is True
    assert _centre_colour(tray.icon()) == ERROR_COLOR
    assert tray.toolTip() == ERROR_TOOLTIP_PREFIX + "boom"

    tray.set_error(None)
    assert tray.has_error is False
    assert _centre_colour(tray.icon()) == ACTIVE_COLOR
    assert tray.toolTip() == "Proofline (active)"


def test_set_error_truncates_long_message(qtbot):
    tray = TrayIcon(enabled=True)
    tray.set_error("x" * LONG_MESSAGE_CHARS)
    assert tray.toolTip() == ERROR_TOOLTIP_PREFIX + "x" * TOOLTIP_MESSAGE_CHARS


def test_error_icon_survives_colour_change(qtbot):
    tray = TrayIcon(enabled=True)
    tray.set_error("boom")
    tray.set_color("#1565c0")
    assert _centre_colour(tray.icon()) == ERROR_COLOR


def test_error_icon_survives_enabled_toggle(qtbot):
    tray = TrayIcon(enabled=True)
    tray.set_error("boom")
    tray.toggle_enabled()
    assert _centre_colour(tray.icon()) == ERROR_COLOR
    tray.set_error(None)
    assert _centre_colour(tray.icon()) == PAUSED_COLOR
