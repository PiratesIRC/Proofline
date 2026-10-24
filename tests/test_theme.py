import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from proofline.theme import THEMES, apply_theme, is_dark
from proofline.tray import ACTIVE_COLOR, ICON_SIZE, PAUSED_COLOR, TRAY_COLORS, TrayIcon

# A point inside the badge circle, left of the "P" text.
SAMPLE_X = 5
SAMPLE_Y = 32


@pytest.fixture(autouse=True)
def restore_auto_theme(qapp):
    yield
    apply_theme(qapp, "auto")


class FakeStyleHints:
    def __init__(self) -> None:
        self.calls: list[Qt.ColorScheme] = []

    def setColorScheme(self, scheme: Qt.ColorScheme) -> None:
        self.calls.append(scheme)


def test_themes_constant_lists_all_choices():
    assert THEMES == ("auto", "light", "dark")


def test_apply_light_sets_light_scheme(qapp):
    apply_theme(qapp, "light")
    assert qapp.styleHints().colorScheme() == Qt.ColorScheme.Light
    assert not is_dark(qapp)


def test_apply_dark_sets_dark_scheme(qapp):
    apply_theme(qapp, "dark")
    assert qapp.styleHints().colorScheme() == Qt.ColorScheme.Dark
    assert is_dark(qapp)


def test_auto_follows_system_by_requesting_unknown(qapp, monkeypatch):
    fake = FakeStyleHints()
    monkeypatch.setattr(qapp, "styleHints", lambda: fake)
    apply_theme(qapp, "auto")
    assert fake.calls == [Qt.ColorScheme.Unknown]


def test_unknown_theme_name_raises(qapp):
    with pytest.raises(ValueError):
        apply_theme(qapp, "sepia")


def _active_pixel(tray: TrayIcon) -> str:
    image = tray.icon().pixmap(ICON_SIZE, ICON_SIZE).toImage()
    return QColor(image.pixel(SAMPLE_X, SAMPLE_Y)).name()


def test_tray_colour_choices_are_valid_colours():
    assert all(QColor(hex_value).isValid() for hex_value in TRAY_COLORS.values())
    assert TRAY_COLORS["Green"] == ACTIVE_COLOR


def test_set_color_changes_active_icon(qapp):
    tray = TrayIcon(enabled=True)
    assert _active_pixel(tray) == ACTIVE_COLOR
    tray.set_color(TRAY_COLORS["Red"])
    assert _active_pixel(tray) == TRAY_COLORS["Red"]


def test_set_color_keeps_paused_icon_grey(qapp):
    tray = TrayIcon(enabled=False)
    tray.set_color(TRAY_COLORS["Red"])
    assert _active_pixel(tray) == PAUSED_COLOR


def test_set_color_rejects_invalid_colour(qapp):
    tray = TrayIcon(enabled=True)
    with pytest.raises(ValueError):
        tray.set_color("not-a-colour")
