from dataclasses import replace

import pytest
from PyQt6.QtCore import QPoint, QRect, QSize
from PyQt6.QtWidgets import QPushButton

from proofline.config import LANGUAGES
from proofline.tray_flyout import (
    CHECKING_OFF,
    CHECKING_ON,
    PAUSE_HOUR,
    PAUSE_TODAY,
    FlyoutState,
    TrayFlyout,
    flyout_position,
)

BASE = FlyoutState(
    enabled=True,
    picky=False,
    language="en-US",
    server_ok=True,
    server_message="Connected to lan-server",
    current_app="notepad.exe",
    current_app_status="Being checked",
)
AVAILABLE = QRect(0, 0, 1920, 1040)
BOTTOM_ICON = QRect(1850, 1050, 24, 24)
FLYOUT_SIZE = QSize(360, 400)
SIGNAL_NAMES = (
    "checking_mode_chosen",
    "picky_toggled",
    "language_chosen",
    "disable_app_requested",
    "enable_app_requested",
    "pick_field_requested",
    "settings_requested",
    "quit_requested",
)


@pytest.fixture
def flyout(qtbot):
    widget = TrayFlyout()
    qtbot.addWidget(widget)
    widget.set_state(BASE)
    return widget


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


def _tile(flyout: TrayFlyout, title: str) -> QPushButton:
    matches = [
        tile for tile in flyout.findChildren(QPushButton, "tile") if tile.text().startswith(title)
    ]
    assert len(matches) == 1
    return matches[0]


def _button(flyout: TrayFlyout, text: str) -> QPushButton:
    matches = [button for button in flyout.findChildren(QPushButton) if button.text() == text]
    assert len(matches) == 1
    return matches[0]


def _gear(flyout: TrayFlyout) -> QPushButton:
    matches = [b for b in flyout.findChildren(QPushButton) if b.accessibleName() == "Settings"]
    assert len(matches) == 1
    return matches[0]


# ----- set_state reflects every field ----------------------------------------


def test_toggle_tiles_reflect_checked_and_subtitles(flyout):
    flyout.set_state(replace(BASE, enabled=False, picky=True))

    checking = _tile(flyout, "Checking")
    assert not checking.isChecked()
    assert checking.text().endswith("Off")
    picky = _tile(flyout, "Picky mode")
    assert picky.isChecked()
    assert picky.text() == "Picky mode\nExtra style tips: On"


def test_checking_tile_shows_a_pause_with_its_end(flyout):
    flyout.set_state(replace(BASE, enabled=False, paused_until="2:45 PM"))

    tile = _tile(flyout, "Checking")
    assert tile.text() == "Checking\nPaused until 2:45 PM"
    assert not tile.isChecked()


def test_there_is_no_separate_pause_tile(flyout):
    assert len(flyout.findChildren(QPushButton, "tile")) == 3


def test_language_tile_shows_display_name(flyout):
    assert _tile(flyout, "Language").text().endswith(LANGUAGES["en-US"])


def test_language_tile_shows_unknown_code_verbatim(flyout):
    flyout.set_state(replace(BASE, language="xx-YY"))

    assert _tile(flyout, "Language").text().endswith("xx-YY")


def test_current_app_shows_disable_button(flyout):
    assert not _button(flyout, "Turn off in this app").isHidden()
    assert _button(flyout, "Turn back on").isHidden()
    assert _button(flyout, "Turn off in this app").isEnabled()
    assert _button(flyout, "Add a text field…").isEnabled()


def test_current_app_shows_turn_back_on_when_disabled(flyout):
    flyout.set_state(replace(BASE, current_app_disabled=True))

    assert _button(flyout, "Turn off in this app").isHidden()
    assert not _button(flyout, "Turn back on").isHidden()


def test_current_app_without_app_disables_app_button(flyout):
    flyout.set_state(replace(BASE, current_app="", current_app_status=""))

    assert not _button(flyout, "Turn off in this app").isHidden()
    assert not _button(flyout, "Turn off in this app").isEnabled()


@pytest.mark.parametrize(
    ("server_ok", "message", "expected"),
    [
        (True, "Connected to lan-server", "● Connected to lan-server"),
        (False, "Connection refused", "⚠ Connection refused"),
        (None, "ignored", "Checking connection…"),
    ],
)
def test_server_status_text(flyout, server_ok, message, expected):
    flyout.set_state(replace(BASE, server_ok=server_ok, server_message=message))

    status = flyout._status_label
    assert status.text() == expected


def test_app_name_and_status_are_shown(flyout):
    flyout.set_state(replace(BASE, current_app="chrome.exe", current_app_status="Turned off here"))

    assert flyout._app_name.text() == "chrome.exe"
    assert flyout._app_status.text() == "Turned off here"
    assert not flyout._app_status.isHidden()


def test_no_app_message_is_shown(flyout):
    flyout.set_state(replace(BASE, current_app=""))

    assert flyout._app_name.text() == "No app yet — click into a text box"


def test_set_state_emits_no_signals(qtbot, flyout):
    received = {name: _record(getattr(flyout, name)) for name in SIGNAL_NAMES}

    flyout.set_state(
        FlyoutState(
            enabled=False,
            picky=True,
            language="es",
            paused_until="3:00 PM",
            server_ok=False,
            server_message="down",
            current_app="code.exe",
            current_app_status="Being checked",
            current_app_disabled=True,
        )
    )

    assert all(calls == [] for calls in received.values())


# ----- user actions emit the right signals ------------------------------------


def _checking_actions(flyout):
    return {action.data(): action for action in flyout.checking_menu.actions() if action.data()}


@pytest.mark.parametrize(
    ("enabled", "paused_until", "checked"),
    [(True, "", CHECKING_ON), (False, "", CHECKING_OFF), (False, "2:45 PM", None)],
)
def test_checking_menu_marks_the_current_mode(flyout, enabled, paused_until, checked):
    flyout.set_state(replace(BASE, enabled=enabled, paused_until=paused_until))

    actions = _checking_actions(flyout)
    assert list(actions) == [CHECKING_ON, PAUSE_HOUR, PAUSE_TODAY, CHECKING_OFF]
    assert [mode for mode, action in actions.items() if action.isChecked()] == ([checked] if checked else [])


def test_clicking_the_checking_tile_opens_the_menu_without_toggling(flyout, monkeypatch):
    opened = []
    monkeypatch.setattr(flyout.checking_menu, "popup", lambda point: opened.append(point))
    received = _record(flyout.checking_mode_chosen)

    _tile(flyout, "Checking").click()

    assert opened and received == []
    assert _tile(flyout, "Checking").isChecked()


@pytest.mark.parametrize("mode", [CHECKING_ON, PAUSE_HOUR, PAUSE_TODAY, CHECKING_OFF])
def test_choosing_a_checking_mode_emits_it(flyout, mode):
    received = _record(flyout.checking_mode_chosen)

    _checking_actions(flyout)[mode].trigger()

    assert received == [(mode,)]


def test_picky_tile_emits_toggle(flyout):
    received = _record(flyout.picky_toggled)

    _tile(flyout, "Picky mode").click()

    assert received == [(True,)]


def test_language_menu_lists_every_language_with_current_checked(flyout):
    menu = flyout.language_menu
    actions = menu.actions()

    assert [action.data() for action in actions] == list(LANGUAGES)
    checked = [action.data() for action in actions if action.isChecked()]
    assert checked == ["en-US"]


def test_choosing_language_emits_and_updates_subtitle(flyout):
    received = _record(flyout.language_chosen)
    menu = flyout.language_menu
    spanish = next(action for action in menu.actions() if action.data() == "es")

    spanish.trigger()

    assert received == [("es",)]
    assert _tile(flyout, "Language").text().endswith("Spanish")


def test_disable_app_button_emits_process_name(flyout):
    received = _record(flyout.disable_app_requested)

    _button(flyout, "Turn off in this app").click()

    assert received == [("notepad.exe",)]


def test_enable_app_button_emits_process_name(flyout):
    flyout.set_state(replace(BASE, current_app_disabled=True))
    received = _record(flyout.enable_app_requested)

    _button(flyout, "Turn back on").click()

    assert received == [("notepad.exe",)]


def test_add_field_button_emits_pick_field(flyout):
    received = _record(flyout.pick_field_requested)

    _button(flyout, "Add a text field…").click()

    assert received == [()]


def test_gear_and_more_settings_emit_settings(flyout):
    received = _record(flyout.settings_requested)

    _gear(flyout).click()
    _button(flyout, "More settings").click()

    assert received == [(), ()]


def test_quit_button_emits_quit(flyout):
    received = _record(flyout.quit_requested)

    _button(flyout, "Quit").click()

    assert received == [()]


def test_one_shot_action_hides_flyout(flyout):
    flyout.show()

    _button(flyout, "Quit").click()

    assert flyout.isHidden()


def test_toggle_does_not_hide_flyout(flyout):
    flyout.show()

    _tile(flyout, "Picky mode").click()

    assert not flyout.isHidden()


# ----- flyout_position ----------------------------------------------------------


def test_bottom_right_taskbar_icon_aligns_right_edges_above_taskbar():
    point = flyout_position(BOTTOM_ICON, FLYOUT_SIZE, AVAILABLE)

    # Available bottom is y=1039, so 12 px margin plus the 400 px height puts the top at 628.
    assert point == QPoint(1514, 628)


def test_icon_near_left_edge_is_clamped_inside_available():
    icon = QRect(0, 1050, 24, 24)

    point = flyout_position(icon, FLYOUT_SIZE, AVAILABLE)

    assert point.x() == 12


def test_null_icon_uses_bottom_right_of_available():
    point = flyout_position(QRect(), FLYOUT_SIZE, AVAILABLE)

    assert point == QPoint(1548, 628)


def test_top_taskbar_places_flyout_below_icon():
    available = QRect(0, 48, 1920, 1032)
    icon = QRect(1850, 0, 24, 24)

    point = flyout_position(icon, FLYOUT_SIZE, available)

    assert point.y() == 60


@pytest.mark.parametrize(
    "icon",
    [
        BOTTOM_ICON,
        QRect(0, 1050, 24, 24),
        QRect(1900, 1000, 20, 20),
        QRect(),
        QRect(960, 500, 1, 1),
    ],
)
def test_flyout_always_inside_available(icon):
    point = flyout_position(icon, FLYOUT_SIZE, AVAILABLE)

    assert AVAILABLE.contains(QRect(point, FLYOUT_SIZE))


def test_show_at_shows_widget_at_computed_position(flyout):
    flyout.show_at(BOTTOM_ICON, AVAILABLE)
    try:
        assert flyout.isVisible()
        assert flyout.pos() == flyout_position(BOTTOM_ICON, flyout.size(), AVAILABLE)
    finally:
        flyout.hide()


def test_left_taskbar_places_flyout_beside_it_aligned_to_icon_bottom():
    available = QRect(48, 0, 1872, 1080)
    icon = QRect(12, 1000, 24, 24)

    point = flyout_position(icon, FLYOUT_SIZE, available)

    assert point == QPoint(60, 624)  # 1023 - 400 + 1


def test_right_taskbar_places_flyout_beside_it_aligned_to_icon_bottom():
    available = QRect(0, 0, 1872, 1080)
    icon = QRect(1884, 1000, 24, 24)

    point = flyout_position(icon, FLYOUT_SIZE, available)

    assert point == QPoint(1872 - 12 - 360, 624)


def test_side_taskbar_icon_near_top_is_clamped_inside_available():
    available = QRect(48, 0, 1872, 1080)
    icon = QRect(12, 20, 24, 24)

    point = flyout_position(icon, FLYOUT_SIZE, available)

    assert point.y() == 12
    assert available.contains(QRect(point, FLYOUT_SIZE))


def test_flyout_requests_rounded_corners(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr("proofline.tray_flyout.round_corners", calls.append)

    widget = TrayFlyout()
    qtbot.addWidget(widget)

    assert calls == [widget]


def test_tiles_are_tall_enough_for_two_lines(flyout):
    """The style sheet's button min-height used to override setMinimumHeight, clipping tile text."""
    flyout.show_at(QRect(1800, 1050, 24, 24), QRect(0, 0, 1920, 1040))
    for tile in flyout.findChildren(QPushButton, "tile"):
        assert tile.height() >= 64
        assert tile.height() >= 2 * tile.fontMetrics().height()


def test_quit_is_a_plain_link(flyout):
    assert _button(flyout, "Quit").objectName() == "linkButton"
