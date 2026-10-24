from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from proofline.app import LanguageToolApp
from proofline.config import Config, load_config, save_config
from proofline.health import NOTICE_MIN_GAP_S, OutageNotices
from proofline.tray import TrayIcon, make_icon


def actions_by_text(tray):
    return {a.text(): a for a in tray.contextMenu().actions() if a.text()}


def test_make_icon_produces_an_image(qapp):
    assert not make_icon("#2e7d32").isNull()


def test_tray_menu_emits_signals(qtbot, qapp):
    tray = TrayIcon(enabled=True)
    actions = actions_by_text(tray)

    with qtbot.waitSignal(tray.settings_requested):
        actions["Settings…"].trigger()
    with qtbot.waitSignal(tray.quit_requested):
        actions["Quit"].trigger()
    with qtbot.waitSignal(tray.enabled_toggled) as blocker:
        actions["Checking enabled"].trigger()
    assert blocker.args == [False]
    assert "paused" in tray.toolTip()


@pytest.fixture
def app(qapp, tmp_path):
    config_path = tmp_path / "config.json"
    save_config(Config(server_url="https://lt.example/v2/check"), config_path)
    lt_app = LanguageToolApp(
        MagicMock(),
        config_path,
        monitor=MagicMock(),
        overlay=MagicMock(),
        integration=MagicMock(),
        health=MagicMock(),
        quick=MagicMock(),
        updates=MagicMock(current_info=MagicMock(return_value=None)),  # never reaches GitHub
        usage=MagicMock(),  # never reaches the usage counter
    )
    lt_app.config_path = config_path
    return lt_app


def test_config_changes_reach_monitor(app):
    actions_by_text(app._tray)["Checking enabled"].trigger()
    app._monitor.set_config.assert_called_with(app.config)
    assert app.config.enabled is False


def test_server_failure_notifies_once_per_outage_and_rate_limits(app, monkeypatch):
    now = [1000.0]
    app._outage_notices = OutageNotices(clock=lambda: now[0])
    shown = []
    monkeypatch.setattr(app._tray, "showMessage", lambda *args: shown.append(args[1]))
    app._on_check_failed("Could not connect")
    app._on_check_failed("No response")  # same outage, different text: no new notification
    app._on_server_healthy()
    now[0] += 60
    app._on_check_failed("Could not connect")  # new outage within the gap: skipped
    app._on_server_healthy()
    now[0] += NOTICE_MIN_GAP_S
    app._on_check_failed("No response")  # new outage after the gap: notified
    assert shown == ["Could not connect", "No response"]


def test_app_loads_config_from_path(app):
    assert app.config.server_url == "https://lt.example/v2/check"


def test_tray_toggle_persists_enabled_state(app):
    actions_by_text(app._tray)["Checking enabled"].trigger()
    assert app.config.enabled is False
    assert load_config(app.config_path).enabled is False


def test_toggle_survives_write_failure(app, monkeypatch):
    def fail(*_):
        raise OSError("locked")

    monkeypatch.setattr("proofline.app.save_config", fail)
    actions_by_text(app._tray)["Checking enabled"].trigger()
    assert app.config.enabled is False


def test_quit_hides_tray_and_quits(app):
    app.start()
    actions_by_text(app._tray)["Quit"].trigger()
    assert not app._tray.isVisible()
    app._monitor.start.assert_called_once()
    app._monitor.stop.assert_called_once()
    app._qt_app.quit.assert_called_once()


def test_saving_debug_mode_switches_text_logging(app):
    from dataclasses import replace

    from proofline.logging_setup import set_debug_mode, text_logging_enabled

    try:
        app._save(replace(app.config, debug_mode=True))
        assert text_logging_enabled()
        app._save(replace(app.config, debug_mode=False))
        assert not text_logging_enabled()
    finally:
        set_debug_mode(False)


def test_start_applies_integration_and_quit_shuts_it_down(app):
    app.start()
    app._integration.apply.assert_called_once_with(app.config)
    actions_by_text(app._tray)["Quit"].trigger()
    app._integration.shutdown.assert_called_once()


def test_config_change_passes_previous_config_to_integration(app):
    before = app.config
    actions_by_text(app._tray)["Checking enabled"].trigger()
    app._integration.apply.assert_called_with(app.config, before)
    app._overlay.on_config_changed.assert_called()


@pytest.mark.parametrize(
    ("signal", "value", "field"),
    [("add_word_requested", "Dispatcharr", "personal_dictionary"), ("disable_rule_requested", "R1", "disabled_rules")],
)
def test_overlay_dictionary_and_rule_requests_are_saved(app, signal, value, field):
    handler = {"add_word_requested": app._add_word, "disable_rule_requested": app._disable_rule}[signal]
    handler(value)
    assert value in getattr(app.config, field)
    assert value in getattr(load_config(app.config_path), field)


def test_hotkeys_toggle_and_check_now(app):
    app._on_hotkey("toggle")
    assert app.config.enabled is False
    app._on_hotkey("check_now")
    app._monitor.request_check_now.assert_called_once()


def test_startup_checks_server_and_unhealthy_shows_tray_error(app, monkeypatch):
    shown = []
    monkeypatch.setattr(app._tray, "showMessage", lambda *args: shown.append(args[1]))
    app.start()
    app._health.check_now.assert_called_once()
    app._on_server_unhealthy("Could not connect to http://lan-server:8081/v2/check.")
    assert app._tray.has_error
    assert "lan-server" in app._tray.toolTip()
    assert len(shown) == 1
    app._on_server_healthy()
    assert not app._tray.has_error


def test_changing_server_rechecks_health(app):
    app._save(replace(app.config, server_url="https://other.example/v2/check"))
    app._health.check_now.assert_called_once()
    app._save(replace(app.config, debounce_ms=1500))
    app._health.check_now.assert_called_once()  # unrelated change: no new probe


def test_setup_hint_shown_once_and_remembered(app, monkeypatch):
    from proofline.setup_hints import SetupHint

    shown = []
    monkeypatch.setattr(app._tray, "showMessage", lambda *args: shown.append(args[0]))
    hint = SetupHint("java-access-bridge", "Enable Java Access Bridge", "Run jabswitch -enable.")
    app._on_setup_hint(hint)
    app._on_setup_hint(hint)
    assert shown == ["Enable Java Access Bridge"]
    assert load_config(app.config_path).shown_hints == ("java-access-bridge",)


def test_picker_adds_custom_field_and_always_check_app(app):
    app._add_custom_field("erp.exe|PaneControl|TEditor")
    app._always_check_app("MSTSC.EXE")
    saved = load_config(app.config_path)
    assert saved.custom_fields == ("erp.exe|PaneControl|TEditor",)
    assert saved.always_check_apps == ("MSTSC.EXE",)
    assert "mstsc.exe" not in [a.lower() for a in saved.disabled_apps]


def test_tray_has_add_text_field_action(qtbot, app):
    with qtbot.waitSignal(app._tray.pick_field_requested):
        actions_by_text(app._tray)["Add a text field…"].trigger()


@pytest.mark.parametrize(
    ("handler", "field", "value"),
    [("_add_word", "personal_dictionary", "Thsi"), ("_disable_rule", "disabled_rules", "R1"),
     ("_disable_app", "disabled_apps", "erp.exe"), ("_disable_window", "disabled_windows", "Budget")],
)
def test_undo_removes_what_the_popup_added(app, handler, field, value):
    getattr(app, handler)(value)
    assert value in getattr(app.config, field)
    app._undo(field, value)
    assert value not in getattr(app.config, field)
    assert value not in getattr(load_config(app.config_path), field)


def test_new_release_is_notified_once_across_restarts(app, monkeypatch):
    shown = []
    monkeypatch.setattr(app._tray, "showMessage", lambda *args: shown.append(args[1]))
    app._on_newer_version("0.2.0")
    app._on_newer_version("0.2.0")
    assert len(shown) == 1 and "0.2.0" in shown[0]
    assert "update-0.2.0" in load_config(app.config_path).shown_hints


def test_applied_correction_is_counted_and_failed_one_is_not(app):
    app._on_replace_finished(False, "Text changed; nothing replaced")
    app._usage.on_correction_applied.assert_not_called()
    app._on_replace_finished(True, "")
    app._usage.on_correction_applied.assert_called_once()


def test_usage_reporting_starts_and_follows_the_setting(app):
    app.start()
    app._usage.start.assert_called_once()
    app._save(replace(app.config, share_usage_counts=False))
    app._usage.on_setting_changed.assert_called_once()
    app._quit()
    app._usage.stop.assert_called_once()


def test_check_now_forces_an_update_check(app):
    app._settings.update_check_requested.emit()
    app._updates.check_now.assert_called_with(force=True)


def _app_at(path):
    return LanguageToolApp(MagicMock(), path, monitor=MagicMock(), overlay=MagicMock(), integration=MagicMock(),
                           health=MagicMock(), quick=MagicMock(),
                           updates=MagicMock(current_info=MagicMock(return_value=None)), usage=MagicMock())


def test_fresh_install_shows_the_welcome_once(qtbot, tmp_path):
    fresh = _app_at(tmp_path / "config.json")
    fresh.start()
    assert fresh._welcome is not None and fresh._welcome.isVisible()
    fresh._welcome.close()
    assert load_config(tmp_path / "config.json").welcome_shown


def test_existing_settings_skip_the_welcome(app):
    app.start()
    assert app._welcome is None


def test_clicking_a_notification_opens_its_link(app, monkeypatch):
    from proofline.setup_hints import SetupHint

    opened, shown = [], []
    monkeypatch.setattr("proofline.app.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    monkeypatch.setattr(app._tray, "showMessage", lambda *args: shown.append(args[1]))
    app._on_setup_hint(SetupHint("google-docs", "Turn on screen reader support", "Press Ctrl+Alt+Z.", "https://help.example"))
    assert "Click for details" in shown[-1]
    app._tray.messageClicked.emit()
    assert opened == ["https://help.example"]
    app._notify("Could not connect")  # a plain warning has no link
    app._tray.messageClicked.emit()
    assert opened == ["https://help.example"]


def test_fix_first_shortcut_applies_the_first_suggestion(app):
    assert app.config.hotkey_fix_first == "ctrl+alt+j"
    app._on_hotkey("fix_first")
    app._overlay.apply_first_suggestion.assert_called_once()
