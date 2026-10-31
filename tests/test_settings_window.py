import threading
import winreg
from dataclasses import replace

import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QGuiApplication, QIcon, QPixmap

from proofline import lt_client
from proofline.app_identity import register_app_id
from proofline.config import Config, ConfigError, validate
from proofline.lt_client import ERROR_CONNECT, LanguageToolError
from proofline.settings_window import SettingsWindow
from proofline.ui_kit import (
    DARK,
    LIGHT,
    ExpanderCard,
    InfoBar,
    ToggleSwitch,
    stylesheet,
)

INSECURE = "http://lan-server:8081/v2/check"


class Store:
    """Stands in for the app: current config plus a record of every save."""

    def __init__(self, config):
        self.config = validate(config)
        self.saves = []
        self.error = None

    def save(self, config):
        if self.error:
            raise self.error
        self.config = validate(config)
        self.saves.append(self.config)
        return self.config


@pytest.fixture
def store():
    return Store(Config(server_url=INSECURE))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Save runs a connection test; keep every test off the network unless it patches check again."""
    patch_check(monkeypatch, lambda: ())


@pytest.fixture
def window(qtbot, store, tmp_path):
    w = SettingsWindow(lambda: store.config, store.save, tmp_path / "logs")
    qtbot.addWidget(w)
    w.show_settings()
    w.asked = []
    w.confirm_insecure = lambda url: w.asked.append(url) or True
    return w


def test_opening_loads_values_without_saving(window, store):
    assert window.general.url_text == INSECURE
    assert store.saves == []


@pytest.mark.parametrize(
    ("action", "field", "expected"),
    [
        (lambda w: w.general._autostart.setChecked(True), "start_with_windows", True),
        (lambda w: w.general._language.setCurrentIndex(w.general._language.findData("es")), "language", "es"),
        (lambda w: w.checking._delay.setCurrentIndex(w.checking._delay.findData(2000)), "debounce_ms", 2000),
        (lambda w: w.checking._min_words.setValue(3), "min_words", 3),
        (lambda w: w.checking._picky.setChecked(True), "picky", True),
        (lambda w: w.checking._hidden.setChecked(False), "flag_hidden_characters", False),
        (lambda w: w.checking._words.add_item("Dispatcharr"), "personal_dictionary", ("Dispatcharr",)),
        (lambda w: w.checking._rules.add_item("WHITESPACE_RULE"), "disabled_rules", ("WHITESPACE_RULE",)),
        (lambda w: w.checking._categories.box("STYLE").click(), "disabled_categories", ("STYLE",)),
        (lambda w: w.apps._lists["always_check_apps"][1].add_item("erp.exe"), "always_check_apps", ("erp.exe",)),
        (lambda w: w.appearance._theme.setCurrentIndex(w.appearance._theme.findData("dark")), "theme", "dark"),
        (lambda w: w.appearance._tray_color.setCurrentIndex(1), "tray_color", "#1565c0"),
        (lambda w: w.appearance._badge.setChecked(False), "badge_always_visible", False),
        (lambda w: w.appearance._underlines.setChecked(False), "show_underlines", False),
        (lambda w: w.advanced._debug.setChecked(True), "debug_mode", True),
        (lambda w: w.advanced._updates.setChecked(False), "check_for_updates", False),
        (lambda w: w.advanced._share_usage.setChecked(False), "share_usage_counts", False),
    ],
)
def test_changes_save_immediately(window, store, action, field, expected):
    action(window)
    assert getattr(store.saves[-1], field) == expected


def test_remove_from_list_saves(window, store):
    editor = window.apps._lists["disabled_apps"][1]
    editor._list.item(0).setSelected(True)
    editor._remove_button.click()
    assert "KeePass.exe" not in store.saves[-1].disabled_apps


def test_add_recommended_exclusions_restores_defaults(window, store):
    store.config = replace(store.config, disabled_apps=(), disabled_windows=())
    window.reload()
    window.apps._add_recommended()
    assert "KeePass.exe" in store.config.disabled_apps
    assert "Password" in store.config.disabled_windows


def test_server_save_unchanged_url_does_nothing(window, store):
    window.general._save_button.click()
    assert store.saves == [] and window.asked == []


def test_server_save_to_other_insecure_host_asks_then_saves(window, store):
    window.general._url.setText("http://other-server:8081/v2")
    window.general._save_button.click()
    assert window.asked == ["http://other-server:8081/v2/check"]
    assert store.config.server_url == "http://other-server:8081/v2/check"


def test_declining_insecure_prompt_keeps_old_url(window, store):
    window.confirm_insecure = lambda url: False
    window.general._url.setText("http://other-server:8081/v2")
    window.general._save_button.click()
    assert store.config.server_url == INSECURE


def test_https_url_saves_without_prompt(window, store):
    window.general._url.setText("https://lt.example")
    window.general._save_button.click()
    assert window.asked == []
    assert store.config.server_url == "https://lt.example/v2/check"


def test_invalid_url_shows_error(window, store):
    window.general._url.setText("not a url")
    window.general._save_button.click()
    assert window.error_bar.isVisibleTo(window)
    assert store.saves == []


def test_insecure_bar_follows_url_and_save_button_enables_on_edit(window):
    assert window.general.insecure_bar.isVisibleTo(window)
    assert not window.general._save_button.isEnabled()
    window.general._url.setText("https://lt.example")
    assert not window.general.insecure_bar.isVisibleTo(window)
    assert window.general._save_button.isEnabled()


@pytest.mark.parametrize(("error", "text"), [(OSError("disk full"), "disk full"), (ConfigError("bad"), "bad")])
def test_save_errors_show_in_error_bar(window, store, error, text):
    store.error = error
    window.general._autostart.setChecked(True)
    assert window.error_bar.isVisibleTo(window)
    assert text in window.error_bar.message


@pytest.mark.parametrize(
    ("toggle", "check_now", "ok"),
    [("ctrl+alt+p", "ctrl+alt+l", True), ("", "CTRL+ALT+L", True), ("ctrl+alt", "", False), ("ctrl+alt+p", "ctrl+alt+p", False)],
)
def test_shortcuts_apply_with_validation(window, store, toggle, check_now, ok):
    window.shortcuts._edits["hotkey_toggle"].set_hotkey(toggle)
    window.shortcuts._edits["hotkey_check_now"].set_hotkey(check_now)
    window.shortcuts.apply_shortcuts()
    if ok:
        assert (store.config.hotkey_toggle, store.config.hotkey_check_now) == (toggle, check_now.lower())
        assert window.shortcuts.error_bar.isHidden()
    else:
        assert store.saves == []
        assert not window.shortcuts.error_bar.isHidden()


def test_search_jumps_to_matching_page_and_hides_others(window):
    window.search.setText("dictionary")
    assert window.nav.currentRow() == 1  # Checking
    assert window.nav.item(0).isHidden()
    assert not window.checking._dictionary.isHidden()
    window.search.setText("")
    assert not any(window.nav.item(i).isHidden() for i in range(window.nav.count()))


def test_config_changed_reloads_but_keeps_half_typed_url(window, store):
    window.general._url.setText("http://half-typed")
    store.config = replace(store.config, picky=True)
    window.config_changed()
    assert window.checking._picky.isChecked()
    assert window.general.url_text == "http://half-typed"


def patch_check(monkeypatch, fn):
    monkeypatch.setattr(lt_client.LanguageToolClient, "check", lambda self, text: fn())


def status_text(window):
    return window.general.status_label.text()


def test_connection_test_ready_is_green(qtbot, window, monkeypatch):
    patch_check(monkeypatch, lambda: ("m1",))
    window.general.test_connection()
    qtbot.waitUntil(lambda: "Ready" in status_text(window))
    assert window.general.status_label.objectName() == "statusOk"


def test_connection_test_no_correction_is_orange(qtbot, window, monkeypatch):
    patch_check(monkeypatch, lambda: ())
    window.general.test_connection()
    qtbot.waitUntil(lambda: "not corrected" in status_text(window))
    assert window.general.status_label.objectName() == "statusWarn"


def test_connection_test_unreachable_is_red(qtbot, window, monkeypatch):
    def fail():
        raise LanguageToolError("Could not connect", ERROR_CONNECT)

    patch_check(monkeypatch, fail)
    window.general.test_connection()
    qtbot.waitUntil(lambda: "Can't connect" in status_text(window))
    assert window.general.status_label.objectName() == "statusError"


def test_editing_url_hides_old_status(qtbot, window, monkeypatch):
    patch_check(monkeypatch, lambda: ("m1",))
    window.general.test_connection()
    qtbot.waitUntil(lambda: "Ready" in status_text(window))
    window.general._url.setText("http://other")
    assert window.general.status_label.isHidden()


def test_saving_server_runs_the_test(qtbot, window, monkeypatch):
    patch_check(monkeypatch, lambda: ("m1",))
    window.general._url.setText("https://lt.example")
    window.general._save_button.click()
    qtbot.waitUntil(lambda: "Ready" in status_text(window))


def test_stale_connection_result_is_discarded(qtbot, window, monkeypatch):
    release = threading.Event()
    patch_check(monkeypatch, lambda: release.wait(5) and ("m1",))
    window.general.test_connection()
    window.general._url.setText("http://other")
    release.set()
    QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(50)
    assert "Ready" not in status_text(window)


@pytest.mark.clipboard
def test_advanced_copy_report_and_clear_logs(window, monkeypatch):
    window.advanced.copy_report()
    assert QGuiApplication.clipboard().text().startswith("Proofline diagnostic report")
    monkeypatch.setattr(window.advanced, "confirm_clear_logs", lambda: False)
    window.advanced.clear_logs()
    assert "copied" in window.advanced.result_bar.message


def test_advanced_shows_languagetool_attribution(window):
    link = window.advanced.attribution_link
    assert 'href="https://languagetool.org"' in link.text()
    assert link.openExternalLinks()
    assert window.advanced.filter("affiliated")


def test_pick_field_button_forwards_signal(qtbot, window):
    with qtbot.waitSignal(window.pick_field_requested):
        window.apps.pick_field_requested.emit()


def test_toggle_switch_and_expander(qtbot):
    switch = ToggleSwitch("demo")
    qtbot.addWidget(switch)
    switch.click()
    assert switch.isChecked()
    card = ExpanderCard("Apps")
    qtbot.addWidget(card)
    assert not card.is_expanded
    card.set_expanded(True)
    assert card.is_expanded


def test_info_bar_rejects_unknown_severity(qtbot):
    with pytest.raises(ValueError):
        InfoBar("panic")


def test_stylesheet_uses_theme_tokens():
    assert DARK.window in stylesheet(DARK, "#2e7d32")
    assert LIGHT.window in stylesheet(LIGHT, "#2e7d32")


def test_register_app_id_writes_name_and_icon(qapp, tmp_path):
    parent = r"Software\ProoflineTest\AppUserModelId"
    pixmap = QPixmap(32, 32)
    pixmap.fill()
    icon_path = tmp_path / "icon.png"
    try:
        register_app_id(QIcon(pixmap), "Test.App", icon_path, parent)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\Test.App") as key:
            assert winreg.QueryValueEx(key, "DisplayName")[0] == "Proofline"
        assert icon_path.exists()
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{parent}\Test.App")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, parent)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\ProoflineTest")


def test_update_status_shows_in_about_card(window):
    window.set_update_status("Update available: 0.2.0 (current: v0.1.0)")
    assert "Update available: 0.2.0" in window.advanced.about_card.description_label.text()


def test_opening_settings_never_checks_github(window, monkeypatch):
    calls = []
    monkeypatch.setattr("proofline.update_check.requests.get", lambda *a, **k: calls.append(a))
    window.show_settings()
    window.nav.setCurrentRow(window.pages.index(window.advanced))
    assert calls == []


def test_usage_sharing_switch_appears_once_and_names_what_is_sent(window):
    cards = [c for c in window.advanced.cards if c.title_label.text() == "Share anonymous usage counts"]
    assert len(cards) == 1
    text = cards[0].description_label.text()
    assert "plugin-stats.dpas.workers.dev" in text and "No text you type" in text


@pytest.mark.parametrize("tokens", [LIGHT, DARK])
def test_links_use_the_readable_accent(window, monkeypatch, tokens):
    from PyQt6.QtGui import QPalette

    from proofline import ui_kit

    monkeypatch.setattr(ui_kit, "current_tokens", lambda: tokens)
    window.refresh_style()
    link = window.advanced.attribution_link.palette().color(QPalette.ColorRole.Link).name()
    assert link == ui_kit.readable_accent(window._config_provider().tray_color, tokens)


def test_check_now_button_requests_a_check_and_shows_progress(qtbot, window):
    with qtbot.waitSignal(window.update_check_requested):
        window.advanced.check_now_button.click()
    assert "Checking for updates" in window.advanced.about_card.description_label.text()


def test_building_settings_shows_no_stray_windows(qtbot, store, tmp_path):
    """Labels made visible before they had a parent flashed as tiny top-level windows at startup."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QApplication, QWidget

    shown = []

    class Watch(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(type(obj).__name__)
            return False

    watch = Watch()
    QApplication.instance().installEventFilter(watch)
    try:
        w = SettingsWindow(lambda: store.config, store.save, tmp_path / "logs")
        qtbot.addWidget(w)
    finally:
        QApplication.instance().removeEventFilter(watch)
    assert shown == []


def test_fix_first_shortcut_has_a_recorder(window):
    assert window.shortcuts._edits["hotkey_fix_first"].hotkey() == "ctrl+alt+j"


def test_about_card_has_a_help_link(window):
    assert "TROUBLESHOOTING" in window.advanced.help_link.text()


def test_about_card_has_a_whats_new_link(window):
    assert "CHANGELOG.md" in window.advanced.changelog_link.text()


def test_ai_page_is_listed_between_shortcuts_and_advanced(window):
    titles = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert titles.index("AI") == titles.index("Shortcuts") + 1
    assert titles.index("Advanced") == titles.index("AI") + 1


def test_shortcuts_page_has_the_ai_rephrase_row(window, store):
    edit = window.shortcuts._edits["hotkey_ai_rephrase"]
    assert edit.hotkey() == ""
    edit.set_hotkey("ctrl+alt+r")
    window.shortcuts.apply_shortcuts()
    assert store.config.hotkey_ai_rephrase == "ctrl+alt+r"
