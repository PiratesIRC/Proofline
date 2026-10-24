from datetime import datetime

import pytest
from factories import focus_result, snapshot
from PyQt6.QtWidgets import QSystemTrayIcon

from proofline.config import Config, validate
from proofline.quick_settings import (
    STATUS_CHECKED,
    STATUS_NO_FIELD,
    STATUS_OFF,
    QuickSettings,
    connected_message,
    pause_label,
)
from proofline.text_snapshot import FocusResult
from proofline.tray import TrayIcon
from proofline.tray_flyout import CHECKING_OFF, CHECKING_ON, PAUSE_HOUR, PAUSE_TODAY


class Harness:
    def __init__(self, qtbot):
        self.config = validate(Config())
        self.tray = TrayIcon(enabled=True)
        self.tray.enabled_toggled.connect(lambda on: self.save(_replace(self.config, enabled=on)))
        self.quick = QuickSettings(lambda: self.config, self.save, self.tray, clock=lambda: datetime(2026, 10, 23, 13, 0))
        qtbot.addWidget(self.quick.flyout)

    def save(self, config):
        self.config = validate(config)
        self.quick.on_enabled_changed(self.config.enabled)


def _replace(config, **changes):
    from dataclasses import replace

    return replace(config, **changes)


@pytest.fixture
def h(qtbot):
    return Harness(qtbot)


def focus(process="notepad.exe", reason="ok via Text", snap=True, title="notes.txt - Notepad"):
    result = focus_result(snapshot(process_name=process) if snap else None, reason=reason)
    return _replace(result, process_name=process, window_title=title)


def test_helpers():
    assert connected_message("http://lan-server:8081/v2/check") == "Connected to lan-server"
    assert pause_label(datetime(2026, 10, 23, 14, 5)) == "2:05 PM"
    assert pause_label(datetime(2026, 10, 24, 0, 0)) == "midnight"


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (focus(), STATUS_CHECKED),
        (focus(reason="disabled for this app/window", snap=False), STATUS_OFF),
        (focus(reason="not a text control (ButtonControl)", snap=False), STATUS_NO_FIELD),
    ],
)
def test_current_app_follows_focus(h, result, status):
    h.quick.on_focus_changed(result)
    state = h.quick.state()
    assert (state.current_app, state.current_app_status) == ("notepad.exe", status)


def test_own_window_and_pause_do_not_replace_current_app(h):
    h.quick.on_focus_changed(focus())
    h.quick.on_focus_changed(FocusResult((), "", "focus is in this app", process_name="python.exe"))
    h.quick.on_focus_changed(FocusResult((), "", "checking paused"))
    assert h.quick.state().current_app == "notepad.exe"


def test_excluded_app_reports_disabled(h):
    h.quick.on_focus_changed(focus(process="mstsc.exe", reason="disabled for this app/window", snap=False))
    state = h.quick.state()
    assert state.current_app_disabled and state.current_app_status == STATUS_OFF


def test_pause_turns_off_and_resume_turns_on(h):
    h.quick.pause()
    assert not h.config.enabled
    assert h.quick.state().paused_until == "2:00 PM"
    h.quick.resume()
    assert h.config.enabled
    assert h.quick.paused_until is None


def test_turning_checking_back_on_cancels_pause(h):
    h.quick.pause()
    h.tray.set_enabled(True)
    assert h.quick.paused_until is None
    assert not h.quick._pause_timer.isActive()


def test_flyout_toggles_save(h):
    h.quick.flyout.picky_toggled.emit(True)
    h.quick.flyout.language_chosen.emit("es")
    assert (h.config.picky, h.config.language) == (True, "es")
    h.quick.flyout.checking_mode_chosen.emit(CHECKING_OFF)
    assert not h.config.enabled


def test_disable_then_enable_app(h):
    h.quick.on_focus_changed(focus(process="erp.exe", title="Orders"))
    h.quick.flyout.disable_app_requested.emit("erp.exe")
    assert "erp.exe" in h.config.disabled_apps
    h.quick.flyout.enable_app_requested.emit("erp.exe")
    assert "erp.exe" not in h.config.disabled_apps
    assert "erp.exe" not in h.config.always_check_apps


def test_enable_app_blocked_by_window_title_adds_always_check(h):
    h.quick.on_focus_changed(focus(process="vivaldi.exe", title="Console Login - Vivaldi"))
    h.quick.flyout.enable_app_requested.emit("vivaldi.exe")
    assert "vivaldi.exe" in h.config.always_check_apps


def test_server_status_shown(h):
    h.quick.on_server_status(False, "Could not connect")
    state = h.quick.state()
    assert (state.server_ok, state.server_message) == (False, "Could not connect")


@pytest.mark.parametrize("signal", ["settings_requested", "pick_field_requested", "quit_requested"])
def test_actions_forwarded(qtbot, h, signal):
    with qtbot.waitSignal(getattr(h.quick, signal)):
        getattr(h.quick.flyout, signal).emit()


def test_show_opens_flyout(h):
    h.quick.show()
    assert h.quick.flyout.isVisible()
    h.quick.flyout.hide()


def test_tray_left_click_requests_flyout(qtbot):
    tray = TrayIcon(enabled=True)
    with qtbot.waitSignal(tray.flyout_requested):
        tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)


def test_pause_is_saved_and_cleared_on_resume(h):
    h.quick.pause()
    assert h.config.paused_until == "2026-10-23T14:00:00"
    h.quick.resume()
    assert h.config.paused_until == ""


def test_turning_checking_back_on_clears_saved_pause(h):
    h.quick.pause()
    h.tray.set_enabled(True)
    assert h.config.paused_until == ""


def _restart(h, **changes):
    """Simulate an app restart with a saved config."""
    h.config = validate(_replace(h.config, **changes))
    h.tray.set_enabled(h.config.enabled)
    h.quick.restore_pause()


def test_restore_keeps_unfinished_pause_with_remaining_time(h):
    _restart(h, enabled=False, paused_until="2026-10-23T13:30:00")
    assert not h.config.enabled
    assert h.quick.state().paused_until == "1:30 PM"
    assert 29 * 60_000 < h.quick._pause_timer.remainingTime() <= 30 * 60_000


def test_restore_resumes_when_pause_has_ended(h):
    _restart(h, enabled=False, paused_until="2026-10-23T12:59:00")
    assert h.config.enabled
    assert h.config.paused_until == ""
    assert h.quick.paused_until is None


def test_restore_clears_stale_pause_when_already_enabled(h):
    _restart(h, enabled=True, paused_until="2026-10-23T13:30:00")
    assert h.config.enabled and h.config.paused_until == ""
    assert not h.quick._pause_timer.isActive()


def test_restore_without_saved_pause_changes_nothing(h):
    _restart(h, enabled=False)
    assert not h.config.enabled
    assert h.quick.paused_until is None


def test_checking_modes_from_the_flyout(h):
    h.quick.flyout.checking_mode_chosen.emit(PAUSE_HOUR)
    assert not h.config.enabled and h.quick.state().paused_until == "2:00 PM"
    h.quick.flyout.checking_mode_chosen.emit(PAUSE_TODAY)
    assert h.quick.state().paused_until == "midnight"
    assert h.config.paused_until == "2026-10-24T00:00:00"
    h.quick.flyout.checking_mode_chosen.emit(CHECKING_ON)
    assert h.config.enabled and h.quick.paused_until is None
    h.quick.flyout.checking_mode_chosen.emit(PAUSE_HOUR)
    h.quick.flyout.checking_mode_chosen.emit(CHECKING_OFF)
    assert not h.config.enabled and h.quick.paused_until is None and h.config.paused_until == ""


@pytest.mark.parametrize("shell", ["explorer.exe", "ShellExperienceHost.exe", "StartMenuExperienceHost.exe", "SearchHost.exe"])
def test_clicking_the_taskbar_keeps_the_last_real_app(h, shell):
    """Opening the flyout moves focus to the taskbar; the card should still show the app you were in."""
    h.quick.on_focus_changed(focus())
    h.quick.on_focus_changed(focus(process=shell, reason="not a text control (PaneControl)", snap=False, title="Taskbar"))
    assert (h.quick.state().current_app, h.quick.state().current_app_status) == ("notepad.exe", STATUS_CHECKED)


def test_a_text_box_in_explorer_still_counts(h):
    h.quick.on_focus_changed(focus())
    h.quick.on_focus_changed(focus(process="explorer.exe", title="Documents"))
    assert h.quick.state().current_app == "explorer.exe"
