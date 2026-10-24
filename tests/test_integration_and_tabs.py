from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from factories import snapshot
from PyQt6.QtCore import QObject, pyqtSignal

from proofline.autostart import AutostartError
from proofline.badge import BadgeState, BadgeWidget
from proofline.config import Config
from proofline.hotkeys import HotkeyError
from proofline.integration import DesktopIntegration
from proofline.lt_client import Match
from proofline.overlay_controller import OverlayController
from proofline.overlay_widgets import IssuesPopup

SPELLING = Match(0, 4, "Possible spelling mistake", "", ("This",), "MORFOLOGIK_RULE_EN_US", "Typos", "Thsi", "TYPOS")
GRAMMAR = Match(5, 3, "Did you mean 'is'?", "", ("is",), "PLURAL_VERB", "Grammar", "are", "GRAMMAR")


class FakeHotkeys(QObject):
    triggered = pyqtSignal(str)

    def __init__(self, taken=()):
        super().__init__()
        self.registered = {}
        self.taken = set(taken)

    def register(self, name, combo):
        if combo in self.taken:
            raise HotkeyError("already used by another app")
        self.registered[name] = combo

    def unregister_all(self):
        self.registered.clear()


@pytest.fixture
def integration(qapp, monkeypatch):
    themes = []
    monkeypatch.setattr("proofline.integration.apply_theme", lambda app, theme: themes.append(theme))
    autostart = MagicMock()
    autostart.is_enabled.return_value = False
    notes = []
    tray = MagicMock()
    hotkeys = FakeHotkeys(taken={"ctrl+alt+l"})
    obj = DesktopIntegration(qapp, tray, notes.append, hotkeys, autostart)
    obj.themes, obj.autostart, obj.notes, obj.tray, obj.fake_hotkeys = themes, autostart, notes, tray, hotkeys
    return obj


def test_startup_applies_everything_and_reports_taken_shortcut(integration):
    integration.apply(Config(theme="dark", tray_color="#1565c0"))
    assert integration.themes == ["dark"]
    integration.tray.set_color.assert_called_once_with("#1565c0")
    assert integration.fake_hotkeys.registered == {"toggle": "ctrl+alt+p"}
    assert any("ctrl+alt+l" in note for note in integration.notes)
    integration.autostart.set_enabled.assert_not_called()  # registry already matches config


def test_later_changes_only_touch_what_changed(integration):
    before = Config()
    integration.apply(replace(before, start_with_windows=True), before)
    integration.autostart.set_enabled.assert_called_once_with(True)
    assert integration.themes == []
    integration.tray.set_color.assert_not_called()


def test_autostart_entry_pointing_elsewhere_is_rewritten(integration):
    integration.autostart.stored_command.return_value = r'"C:\old\pythonw.exe" "main.py"'
    integration.autostart.launch_command.return_value = r'"C:\app\Proofline.exe"'
    integration.apply(Config(start_with_windows=True))
    integration.autostart.set_enabled.assert_called_once_with(True)


def test_autostart_entry_already_current_is_left_alone(integration):
    integration.autostart.stored_command.return_value = r'"C:\app\Proofline.exe"'
    integration.autostart.launch_command.return_value = r'"C:\app\Proofline.exe"'
    integration.apply(Config(start_with_windows=True))
    integration.autostart.set_enabled.assert_not_called()


def test_autostart_turned_off_removes_entry(integration):
    integration.autostart.is_enabled.return_value = True
    integration.apply(Config(), Config(start_with_windows=True))
    integration.autostart.set_enabled.assert_called_once_with(False)


def test_autostart_failure_is_reported(integration):
    integration.autostart.set_enabled.side_effect = AutostartError("registry locked")
    integration.apply(Config(start_with_windows=True), Config())
    assert "registry locked" in integration.notes


def test_hotkey_signal_is_forwarded(qtbot, integration):
    with qtbot.waitSignal(integration.hotkey_triggered) as blocker:
        integration.fake_hotkeys.triggered.emit("check_now")
    assert blocker.args == ["check_now"]


class Harness:
    def __init__(self, qtbot):
        self.config = Config()
        self.badge, self.popup = BadgeWidget(), IssuesPopup()
        qtbot.addWidget(self.badge)
        qtbot.addWidget(self.popup)
        self.controller = OverlayController(lambda: self.config, self.badge, self.popup)
        self.snap = snapshot(text="Thsi are fine.")
        self.controller.on_field_changed(self.snap)
        self.controller.on_checked(self.snap, (SPELLING, GRAMMAR))


def test_dictionary_words_hide_spelling_issues_immediately(qtbot):
    h = Harness(qtbot)
    assert h.badge._count == 2
    h.config = replace(h.config, personal_dictionary=("thsi",))
    h.controller.on_config_changed()
    assert h.badge._count == 1


def test_ignore_and_disabled_rule_hide_issues(qtbot):
    h = Harness(qtbot)
    h.popup.ignore_requested.emit(GRAMMAR)
    assert h.badge._count == 1
    h.config = replace(h.config, disabled_rules=("MORFOLOGIK_RULE_EN_US",))
    h.controller.on_config_changed()
    assert h.badge.state is BadgeState.CLEAN


def test_popup_actions_emit_word_and_rule(qtbot):
    h = Harness(qtbot)
    with qtbot.waitSignal(h.controller.add_word_requested) as word:
        h.popup.add_word_requested.emit(SPELLING)
    with qtbot.waitSignal(h.controller.disable_rule_requested) as rule:
        h.popup.disable_rule_requested.emit(GRAMMAR)
    assert word.args == ["Thsi"]
    assert rule.args == ["PLURAL_VERB"]


def test_add_to_dictionary_only_offered_for_spelling(qtbot):
    h = Harness(qtbot)
    h.badge.clicked.emit()
    labels = [b.text() for b in h.popup.findChildren(type(h.popup._disable_app_button))]
    assert labels.count("Add to dictionary") == 1
    assert labels.count("Ignore for now") == 2
    assert labels.count("Turn off this rule") == 2
