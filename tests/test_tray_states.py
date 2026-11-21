"""The redrawn icon, the tray's update and AI states, the longer right-click menu, release
notes in Settings, the version in the Settings title, and Restart."""

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from factories import focus_result, snapshot
from PyQt6.QtGui import QColor

from proofline import __version__
from proofline import tray as tray_menu
from proofline.ai_client import AiError, AiResult
from proofline.ai_service import NO_KEY_MESSAGE, AiService
from proofline.app import LanguageToolApp
from proofline.app_icon import DOT_COLOR, ICON_SIZES, draw_icon, make_icon
from proofline.config import Config, load_config, save_config, validate
from proofline.quick_settings import QuickSettings
from proofline.restart import (
    RESTART_ARG,
    is_restart,
    restart_command,
    start_new_copy,
)
from proofline.settings_pages import RELEASE_NO_NOTES_TEXT, ReleaseCard
from proofline.settings_window import WINDOW_TITLE, SettingsWindow
from proofline.tray import (
    ACTIVE_COLOR,
    AI_PROBLEM_COLOR,
    ERROR_COLOR,
    ICON_SIZE,
    PAUSED_COLOR,
    TrayIcon,
)
from proofline.tray_flyout import PAUSE_HOUR, PAUSE_TODAY
from proofline.update_check import (
    NOTES_MAX_CHARS,
    RELEASES_PAGE_URL,
    Release,
    VersionInfo,
    cached_info,
    check_for_update,
    clean_notes,
    fetch_latest_release,
)

NOW = 1_800_000_000.0
RELEASE_URL = "https://github.com/PiratesIRC/Proofline/releases/tag/v9.9.9"
OUTDATED_INFO = VersionInfo("outdated", "Update available: 9.9.9 (current: v0.1.0)", "9.9.9",
                            "- Fixed a thing", RELEASE_URL)
FILL_POINT = (5, 32)  # left edge, middle: inside the square, away from the letter and the dot
DOT_POINT = (56, 8)  # the centre of the top right corner dot on a 64 px icon


def colour_at(icon, point, size=ICON_SIZE):
    return icon.pixmap(size, size).toImage().pixelColor(*point).name()


def all_actions(tray):
    found = {}
    for action in tray.contextMenu().actions():
        found[action.text()] = action
        if action.menu() is not None:
            found.update({sub.text(): sub for sub in action.menu().actions()})
    return found


# ----- icon ------------------------------------------------------------------

def test_icon_holds_every_size_drawn_at_that_size(qapp):
    icon = make_icon(ACTIVE_COLOR)
    assert sorted(size.width() for size in icon.availableSizes()) == list(ICON_SIZES)
    assert 16 in ICON_SIZES and 256 in ICON_SIZES


@pytest.mark.parametrize("size", ICON_SIZES)
def test_icon_corners_are_transparent_and_the_middle_edge_is_the_colour(qapp, size):
    image = draw_icon(size, ACTIVE_COLOR).toImage()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(size - 1, size - 1).alpha() == 0
    assert image.pixelColor(max(1, size // 12), size // 2).name() == ACTIVE_COLOR


def test_dot_is_drawn_only_when_asked_for(qapp):
    assert colour_at(make_icon(ACTIVE_COLOR, dot=True), DOT_POINT) == DOT_COLOR
    assert colour_at(make_icon(ACTIVE_COLOR), DOT_POINT) == ACTIVE_COLOR


# ----- tray states -----------------------------------------------------------

def test_update_adds_dot_tooltip_line_and_menu_item(qtbot, qapp):
    tray = TrayIcon(enabled=True)
    assert "Update available: 9.9.9…" not in all_actions(tray) or not all_actions(tray)["Update available: 9.9.9…"].isVisible()
    tray.set_update("9.9.9")
    item = all_actions(tray)["Update available: 9.9.9…"]
    assert item.isVisible()
    assert colour_at(tray.icon(), DOT_POINT) == DOT_COLOR
    assert colour_at(tray.icon(), FILL_POINT) == ACTIVE_COLOR
    assert tray.toolTip() == "Proofline (active)\nUpdate available: 9.9.9"
    with qtbot.waitSignal(tray.menu_action) as blocker:
        item.trigger()
    assert blocker.args == [tray_menu.OPEN_UPDATE]

    tray.set_update(None)
    assert not item.isVisible()
    assert colour_at(tray.icon(), DOT_POINT) == ACTIVE_COLOR
    assert tray.toolTip() == "Proofline (active)"


def test_update_dot_stays_on_the_paused_and_error_icons(qapp):
    tray = TrayIcon(enabled=False)
    tray.set_update("9.9.9")
    assert (colour_at(tray.icon(), FILL_POINT), colour_at(tray.icon(), DOT_POINT)) == (PAUSED_COLOR, DOT_COLOR)
    tray.set_error("boom")
    assert (colour_at(tray.icon(), FILL_POINT), colour_at(tray.icon(), DOT_POINT)) == (ERROR_COLOR, DOT_COLOR)
    assert tray.toolTip().endswith("boom\nUpdate available: 9.9.9")


def test_ai_problem_turns_the_active_icon_amber_and_clears(qapp):
    tray = TrayIcon(enabled=True)
    tray.set_ai_problem("Could not reach Ollama.")
    assert colour_at(tray.icon(), FILL_POINT) == AI_PROBLEM_COLOR
    assert tray.toolTip() == "Proofline (active)\nAI: Could not reach Ollama."
    tray.set_ai_problem(None)
    assert colour_at(tray.icon(), FILL_POINT) == ACTIVE_COLOR
    assert tray.toolTip() == "Proofline (active)"


def test_server_error_and_pause_outrank_the_ai_problem(qapp):
    tray = TrayIcon(enabled=True)
    tray.set_ai_problem("Could not reach Ollama.")
    tray.set_error("boom")
    assert colour_at(tray.icon(), FILL_POINT) == ERROR_COLOR
    assert "AI:" not in tray.toolTip()
    tray.set_error(None)
    tray.set_enabled(False)
    assert colour_at(tray.icon(), FILL_POINT) == PAUSED_COLOR
    assert "AI:" not in tray.toolTip()
    tray.set_enabled(True)
    assert colour_at(tray.icon(), FILL_POINT) == AI_PROBLEM_COLOR


def test_amber_differs_from_every_tray_colour_choice():
    amber = QColor(AI_PROBLEM_COLOR)
    for name, value in tray_menu.TRAY_COLORS.items():
        other = QColor(value)
        distance = abs(amber.red() - other.red()) + abs(amber.green() - other.green()) + abs(amber.blue() - other.blue())
        assert distance > 60, name


# ----- menu ------------------------------------------------------------------

@pytest.mark.parametrize(("text", "name"), [
    ("Pause for 1 hour", tray_menu.PAUSE_HOUR),
    ("Pause for the rest of today", tray_menu.PAUSE_TODAY),
    ("Check the current field now", tray_menu.CHECK_FIELD),
    ("Check for updates", tray_menu.CHECK_UPDATES),
    ("What's new", tray_menu.WHATS_NEW),
    ("Open log folder", tray_menu.OPEN_LOGS),
    ("Copy diagnostic report", tray_menu.COPY_REPORT),
    ("Restart Proofline", tray_menu.RESTART),
])
def test_menu_items_emit_their_action(qtbot, qapp, text, name):
    tray = TrayIcon(enabled=True)
    with qtbot.waitSignal(tray.menu_action) as blocker:
        all_actions(tray)[text].trigger()
    assert blocker.args == [name]


def test_menu_starts_with_the_version_as_a_disabled_line(qapp):
    first = TrayIcon(enabled=True).contextMenu().actions()[0]
    assert first.text() == f"Proofline {__version__}"
    assert not first.isEnabled()


def test_current_app_item_is_hidden_until_an_app_is_known(qtbot, qapp):
    tray = TrayIcon(enabled=True)
    assert not any(text.startswith("Turn o") and action.isVisible() for text, action in all_actions(tray).items())
    tray.set_current_app("notepad.exe", disabled=False)
    item = all_actions(tray)["Turn off in notepad.exe"]
    assert item.isVisible()
    with qtbot.waitSignal(tray.menu_action) as blocker:
        item.trigger()
    assert blocker.args == [tray_menu.TOGGLE_APP]
    tray.set_current_app("notepad.exe", disabled=True)
    assert "Turn on in notepad.exe" in all_actions(tray)
    tray.set_current_app("")
    assert not item.isVisible()


def test_an_ampersand_in_an_app_name_is_not_read_as_a_shortcut_mark(qapp):
    tray = TrayIcon(enabled=True)
    tray.set_current_app("r&d.exe")
    assert "Turn off in r&&d.exe" in all_actions(tray)


# ----- quick settings: the current app in the menu --------------------------

class QuickHarness:
    def __init__(self, qtbot):
        self.config = validate(Config())
        self.tray = TrayIcon(enabled=True)
        self.quick = QuickSettings(lambda: self.config, self.save, self.tray)
        qtbot.addWidget(self.quick.flyout)

    def save(self, config):
        self.config = validate(config)


def test_menu_follows_the_app_in_focus_and_toggles_it(qtbot):
    h = QuickHarness(qtbot)
    assert h.quick.current_app() == ("", False)
    h.quick.toggle_current_app()  # nothing known yet: nothing happens
    assert h.config.disabled_apps == validate(Config()).disabled_apps

    result = focus_result(snapshot(process_name="notepad.exe"), "ok via Text")
    h.quick.on_focus_changed(replace(result, process_name="notepad.exe", window_title="notes.txt - Notepad"))
    assert "Turn off in notepad.exe" in all_actions(h.tray)
    h.quick.toggle_current_app()
    assert "notepad.exe" in h.config.disabled_apps
    assert "Turn on in notepad.exe" in all_actions(h.tray)
    h.quick.toggle_current_app()
    assert "notepad.exe" not in h.config.disabled_apps
    assert "Turn off in notepad.exe" in all_actions(h.tray)


# ----- update check: release notes ------------------------------------------

class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_returns_tag_notes_and_page():
    payload = {"tag_name": "v9.9.9", "body": "- Fixed a thing\r\n- Added a thing", "html_url": RELEASE_URL}
    release = fetch_latest_release(lambda url, headers, timeout: FakeResponse(payload))
    assert release == Release("v9.9.9", "- Fixed a thing\n- Added a thing", RELEASE_URL)


@pytest.mark.parametrize("url", ["https://evil.example/releases/tag/v9.9.9", "javascript:alert(1)", None, 7,
                                 "https://github.com/Someone/Else/releases/tag/v9.9.9"])
def test_a_release_page_outside_this_project_is_dropped(url):
    payload = {"tag_name": "v9.9.9", "html_url": url}
    assert fetch_latest_release(lambda *a, **k: FakeResponse(payload)).url == ""


def test_notes_are_cleaned_and_shortened():
    assert clean_notes(None) == "" and clean_notes(["x"]) == ""
    assert clean_notes("a\x00b\x1b[31mc\x7f\n\td") == "ab[31mc\nd"
    long_notes = clean_notes("x" * (NOTES_MAX_CHARS + 500))
    assert long_notes.startswith("x" * NOTES_MAX_CHARS) and long_notes.endswith("[...]")
    assert len(long_notes) < NOTES_MAX_CHARS + 20


def test_notes_and_page_are_cached_with_the_result(tmp_path):
    path = tmp_path / "version_check.json"
    info = check_for_update("0.1.0", path, NOW, lambda: Release("v9.9.9", "- Fixed a thing", RELEASE_URL))
    assert (info.status, info.notes, info.url) == ("outdated", "- Fixed a thing", RELEASE_URL)
    assert cached_info("0.1.0", path) == info


def test_an_outdated_cache_without_notes_is_fetched_again(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    old_cache = {"timestamp": NOW, "app_version": "0.1.0", "latest_version": "9.9.9",
                 "version_info": {"status": "outdated", "message": "m", "latest": "9.9.9"}}
    path.write_text(json.dumps(old_cache), encoding="utf-8")

    def fetch():
        calls.append(1)
        return Release("v9.9.9", "notes")

    assert check_for_update("0.1.0", path, NOW + 60, fetch).notes == "notes"
    assert check_for_update("0.1.0", path, NOW + 120, fetch).notes == "notes"
    assert len(calls) == 1


# ----- settings --------------------------------------------------------------

def test_settings_title_carries_the_version():
    assert WINDOW_TITLE.startswith(f"Proofline {__version__}")
    assert WINDOW_TITLE.endswith("Settings")


@pytest.fixture
def window(qtbot, tmp_path):
    config = validate(Config())
    w = SettingsWindow(lambda: config, lambda c: c, tmp_path / "logs")
    qtbot.addWidget(w)
    w.show_settings()
    w.nav.setCurrentRow(w.pages.index(w.advanced))
    return w


def test_window_title_is_set_on_the_window(window):
    assert window.windowTitle() == WINDOW_TITLE


def test_release_notes_show_before_the_download_link(window):
    card = window.advanced.release_card
    assert not card.isVisible()
    window.set_release(OUTDATED_INFO)
    assert card.isVisible()
    assert card.title_label.text() == "What's new in 9.9.9"
    assert card.notes_label.text() == "- Fixed a thing"
    assert RELEASE_URL in card.download_link.text()
    layout = card.layout()
    assert layout.indexOf(card.notes_label) < layout.indexOf(card.download_link)
    window.set_release(None)
    assert not card.isVisible()


def test_release_notes_are_never_rendered_as_markup(qtbot):
    card = ReleaseCard()
    qtbot.addWidget(card)
    card.show_release(VersionInfo("outdated", "m", "9.9.9", '<a href="https://evil.example">click</a>'))
    from PyQt6.QtCore import Qt

    assert card.notes_label.textFormat() == Qt.TextFormat.PlainText
    assert not card.notes_label.openExternalLinks()
    assert RELEASES_PAGE_URL in card.download_link.text()  # no page given: the general releases page


def test_release_without_notes_says_so(qtbot):
    card = ReleaseCard()
    qtbot.addWidget(card)
    card.show_release(VersionInfo("outdated", "m", "9.9.9"))
    assert card.notes_label.text() == RELEASE_NO_NOTES_TEXT


def test_search_hides_the_release_card_unless_it_matches(window):
    window.set_release(OUTDATED_INFO)
    card = window.advanced.release_card
    window.advanced.filter("debug")
    assert not card.isVisible()
    assert window.advanced.filter("release")
    assert card.isVisible()
    window.set_release(None)
    window.advanced.filter("")
    assert not card.isVisible()  # an empty search must not bring back a card with no release


# ----- AI problem ------------------------------------------------------------

class Backend:
    def __init__(self, error=None):
        self.error = error

    def send(self, request, model):
        if self.error is not None:
            raise self.error
        return AiResult({"ok": True}, 10, 10)


def ai_service(tmp_path, backend, config, key="sk-test"):
    from datetime import datetime

    return AiService(lambda: config, lambda spec, k, address: backend, lambda pid: key,
                     tmp_path / "ai_usage.jsonl", lambda: datetime(2026, 10, 26, 12, 0))


def ai_request():
    from proofline.ai_setup import key_test_request

    return key_test_request()


def test_no_problem_while_ai_is_off(tmp_path, qapp):
    assert ai_service(tmp_path, Backend(), Config(), key=None).problem() is None


def test_missing_key_is_a_problem_until_one_is_saved(tmp_path, qtbot):
    keys = {"value": None}
    from datetime import datetime

    service = AiService(lambda: Config(ai_enabled=True), lambda *a: Backend(), lambda pid: keys["value"],
                        tmp_path / "ai_usage.jsonl", lambda: datetime(2026, 10, 26, 12, 0))
    assert service.problem() == NO_KEY_MESSAGE
    keys["value"] = "sk-test"
    with qtbot.waitSignal(service.status_changed):
        service.key_changed()
    assert service.problem() is None


@pytest.mark.parametrize("kind", ["auth", "network", "timeout", "server"])
def test_a_failed_key_or_server_is_a_problem_until_a_request_works(tmp_path, qtbot, kind):
    backend = Backend(AiError(kind, f"failed: {kind}"))
    service = ai_service(tmp_path, backend, Config(ai_enabled=True))
    assert service.problem() is None
    with qtbot.waitSignal(service.failed):
        service.submit(ai_request())
    assert service.problem() == f"failed: {kind}"
    service.key_changed()  # auth also marked the key rejected; a saved key clears both
    backend.error = None
    with qtbot.waitSignal(service.finished):
        service.submit(ai_request())
    assert service.problem() is None


@pytest.mark.parametrize("kind", ["rate_limit", "refusal", "bad_response", "rejected", "credit"])
def test_other_failures_do_not_mark_the_tray(tmp_path, qtbot, kind):
    service = ai_service(tmp_path, Backend(AiError(kind, "no")), Config(ai_enabled=True))
    with qtbot.waitSignal(service.failed):
        service.submit(ai_request())
    assert service.problem() is None


def test_a_problem_belongs_to_its_provider(tmp_path, qtbot):
    config = {"value": Config(ai_enabled=True, ai_provider="ollama", ai_models=("ollama=m",),
                              ai_ollama_url="http://127.0.0.1:11434")}
    from datetime import datetime

    service = AiService(lambda: config["value"], lambda *a: Backend(AiError("network", "Could not reach Ollama.")),
                        lambda pid: "sk-test", tmp_path / "ai_usage.jsonl", lambda: datetime(2026, 10, 26, 12, 0))
    with qtbot.waitSignal(service.failed):
        service.submit(ai_request())
    assert service.problem() == "Could not reach Ollama."
    config["value"] = Config(ai_enabled=True)  # switched to the default provider
    assert service.problem() is None


# ----- app wiring ------------------------------------------------------------

@pytest.fixture
def app(qapp, tmp_path):
    config_path = tmp_path / "config.json"
    save_config(Config(server_url="https://lt.example/v2/check"), config_path)
    lt_app = LanguageToolApp(
        MagicMock(), config_path, monitor=MagicMock(), overlay=MagicMock(), integration=MagicMock(),
        health=MagicMock(), quick=MagicMock(),
        updates=MagicMock(current_info=MagicMock(return_value=None)), usage=MagicMock(),
        start_copy=MagicMock(return_value=True),
    )
    lt_app._ai.problem = MagicMock(return_value=None)
    lt_app.config_path = config_path
    lt_app.shown = []
    lt_app._tray.showMessage = lambda *args: lt_app.shown.append(args[1])
    return lt_app


def test_waiting_release_reaches_the_tray_and_settings(app):
    app._updates.current_info.return_value = OUTDATED_INFO
    app._on_update_checked(OUTDATED_INFO)
    assert app._tray.update_version == "9.9.9"
    assert app._settings.advanced.release_card.notes_label.text() == "- Fixed a thing"
    assert app.shown == []  # the background check's notification comes from newer_version, once

    current = VersionInfo("current", "You are up to date (v9.9.9)", "9.9.9")
    app._updates.current_info.return_value = current
    app._on_update_checked(current)
    assert app._tray.update_version is None


def test_notification_names_both_versions_and_is_shown_once(app):
    app._on_newer_version("9.9.9")
    app._on_newer_version("9.9.9")
    assert len(app.shown) == 1
    assert "9.9.9" in app.shown[0] and __version__ in app.shown[0]
    assert "update-9.9.9" in load_config(app.config_path).shown_hints


def test_check_for_updates_from_the_menu_reports_the_result_once(app):
    app._tray.menu_action.emit(tray_menu.CHECK_UPDATES)
    app._updates.check_now.assert_called_with(force=True)
    current = VersionInfo("current", "You are up to date (v0.1.0)", "0.1.0")
    app._on_update_checked(current)
    app._on_update_checked(current)  # a later background check stays quiet
    assert app.shown == ["You are up to date (v0.1.0)"]


def test_menu_check_that_finds_a_release_announces_it_even_if_seen_before(app):
    app._on_newer_version("9.9.9")
    app._updates.current_info.return_value = OUTDATED_INFO
    app._tray.menu_action.emit(tray_menu.CHECK_UPDATES)
    app._on_update_checked(OUTDATED_INFO)
    assert len(app.shown) == 2 and "9.9.9" in app.shown[1]
    assert load_config(app.config_path).shown_hints.count("update-9.9.9") == 1


def test_menu_pause_check_and_app_items_reach_their_owners(app):
    app._tray.menu_action.emit(tray_menu.PAUSE_HOUR)
    app._quick.set_checking_mode.assert_called_with(PAUSE_HOUR)
    app._tray.menu_action.emit(tray_menu.PAUSE_TODAY)
    app._quick.set_checking_mode.assert_called_with(PAUSE_TODAY)
    app._tray.menu_action.emit(tray_menu.CHECK_FIELD)
    app._monitor.request_check_now.assert_called_once()
    app._tray.menu_action.emit(tray_menu.TOGGLE_APP)
    app._quick.toggle_current_app.assert_called_once()


def test_menu_opens_the_release_page_and_the_changelog(app, monkeypatch):
    opened = []
    monkeypatch.setattr("proofline.app.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    app._tray.menu_action.emit(tray_menu.OPEN_UPDATE)
    app._updates.current_info.return_value = OUTDATED_INFO
    app._tray.menu_action.emit(tray_menu.OPEN_UPDATE)
    app._tray.menu_action.emit(tray_menu.WHATS_NEW)
    assert opened[0] == RELEASES_PAGE_URL
    assert opened[1] == RELEASE_URL
    assert opened[2].endswith("CHANGELOG.md")


def test_menu_copies_the_diagnostic_report(app, qapp):
    app._tray.menu_action.emit(tray_menu.COPY_REPORT)
    assert "Proofline diagnostic report" in qapp.clipboard().text()
    assert len(app.shown) == 1


def test_restart_starts_a_copy_then_quits(app):
    app._tray.menu_action.emit(tray_menu.RESTART)
    app._start_new_copy.assert_called_once()
    app._qt_app.quit.assert_called_once()


def test_restart_keeps_running_when_the_copy_cannot_start(app):
    app._start_new_copy.return_value = False
    app._tray.menu_action.emit(tray_menu.RESTART)
    app._qt_app.quit.assert_not_called()
    assert "could not restart" in app.shown[0]


def test_ai_problem_reaches_the_tray_and_clears(app):
    app._ai.problem.return_value = "Could not reach Ollama."
    app._show_ai_state()
    assert app._tray.ai_problem == "Could not reach Ollama."
    app._ai.problem.return_value = None
    app._show_ai_state()
    assert app._tray.ai_problem is None


# ----- restart ---------------------------------------------------------------

def test_restart_command_runs_main_with_the_restart_mark():
    program, arguments = restart_command()
    assert program.lower().endswith(".exe")
    assert arguments[-1] == RESTART_ARG and arguments[0].endswith("main.py")
    assert is_restart(["main.py", RESTART_ARG]) and not is_restart(["main.py"])


@pytest.mark.parametrize(("answer", "expected"), [(True, True), (False, False), ((True, 1234), True), ((False, 0), False)])
def test_start_new_copy_reports_whether_windows_started_it(answer, expected):
    calls = []
    assert start_new_copy(lambda program, arguments: calls.append((program, arguments)) or answer) is expected
    assert calls[0][1][-1] == RESTART_ARG
