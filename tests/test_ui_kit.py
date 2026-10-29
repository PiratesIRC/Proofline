from dataclasses import replace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from proofline import ui_kit
from proofline.ui_kit import (
    DARK,
    LIGHT,
    apply_style,
    contrast_ratio,
    link_colour,
    link_html,
)

LINK_HTML = '<a href="https://example.invalid/help">Help</a>'


def test_contrast_ratio_matches_wcag_extremes():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21, abs=0.01)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#0067c0", "#f3f3f3") == pytest.approx(contrast_ratio("#f3f3f3", "#0067c0"))


@pytest.mark.parametrize("accent", ["#2e7d32", "#0078d4", "#ffd000"])
def test_accent_on_dark_window_is_lightened_then_checked(accent):
    colour = link_colour(accent, DARK)
    assert colour != "#0000ff"  # never Qt's default blue
    assert contrast_ratio(colour, DARK.window) >= ui_kit.LINK_MIN_CONTRAST


def test_accent_with_enough_contrast_is_used_on_light():
    assert link_colour("#2e7d32", LIGHT) == "#2e7d32"  # 4.62:1 on the window


def test_faint_accent_on_light_falls_back_to_theme_link():
    assert link_colour("#ffd000", LIGHT) == LIGHT.link


def test_accent_too_dark_for_dark_mode_uses_theme_link():
    # Lightening a near-black accent does not lift it far enough from the dark window.
    assert link_colour("#202020", DARK) == DARK.link


def test_the_card_background_is_checked_too():
    # Links sit on cards. This card is darker than the window: the accent passes on the window
    # (4.62:1) but not on the card (about 3.9:1), so the theme link colour is used.
    tokens = replace(LIGHT, card="#e0e0e0")
    assert contrast_ratio("#2e7d32", LIGHT.window) >= ui_kit.LINK_MIN_CONTRAST
    assert link_colour("#2e7d32", tokens) == tokens.link


def test_a_stricter_threshold_moves_the_choice(monkeypatch):
    monkeypatch.setattr(ui_kit, "LINK_MIN_CONTRAST", 10)
    assert link_colour("#2e7d32", LIGHT) == LIGHT.link


def test_link_html_adds_the_colour_to_each_anchor():
    styled = link_html(LINK_HTML, "#2e7d32")
    assert styled == '<a style="color:#2e7d32" href="https://example.invalid/help">Help</a>'


def test_link_html_replaces_an_earlier_colour_instead_of_stacking():
    once = link_html(LINK_HTML, "#2e7d32")
    again = link_html(once, "#4ed455")
    assert again == '<a style="color:#4ed455" href="https://example.invalid/help">Help</a>'
    assert link_html(again, "#4ed455") == again


def test_link_html_leaves_text_without_links_alone():
    assert link_html("<b>Plain</b> text", "#2e7d32") == "<b>Plain</b> text"


def test_applied_accent_is_what_the_link_renders_in(qtbot, monkeypatch):
    monkeypatch.setattr(ui_kit, "current_tokens", lambda: LIGHT)
    host = QWidget()
    qtbot.addWidget(host)
    label = QLabel(LINK_HTML)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    QVBoxLayout(host).addWidget(label)
    apply_style(host, "#2e7d32")
    apply_style(host, "#2e7d32")  # a second apply must not stack colours
    assert label.text().count("color:") == 1
    host.show()
    qtbot.waitExposed(host)
    image = label.grab().toImage()
    colours = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert "#2e7d32" in colours and "#0000ff" not in colours


def test_label_without_links_is_not_changed(qtbot, monkeypatch):
    monkeypatch.setattr(ui_kit, "current_tokens", lambda: DARK)
    host = QWidget()
    qtbot.addWidget(host)
    label = QLabel("Just text")
    QVBoxLayout(host).addWidget(label)
    apply_style(host, "#2e7d32")
    assert label.text() == "Just text"


def test_faint_accent_renders_the_theme_link_colour(qtbot, monkeypatch):
    monkeypatch.setattr(ui_kit, "current_tokens", lambda: LIGHT)
    host = QWidget()
    qtbot.addWidget(host)
    label = QLabel(LINK_HTML)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    QVBoxLayout(host).addWidget(label)
    apply_style(host, "#ffd000")
    host.show()
    qtbot.waitExposed(host)
    image = label.grab().toImage()
    colours = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert LIGHT.link in colours and "#ffd000" not in colours and "#0000ff" not in colours


def test_set_link_text_keeps_the_colour_apply_style_gave(qtbot):
    from PyQt6.QtWidgets import QLabel

    from proofline.ui_kit import link_html, set_link_text

    label = QLabel(link_html('<a href="https://a.example">A</a>', "#2e7d32"))
    qtbot.addWidget(label)
    set_link_text(label, '<a href="https://b.example">B</a>')
    assert label.text() == '<a style="color:#2e7d32" href="https://b.example">B</a>'


def test_set_link_text_on_an_unstyled_label_sets_the_text_as_given(qtbot):
    from PyQt6.QtWidgets import QLabel

    from proofline.ui_kit import set_link_text

    label = QLabel("")
    qtbot.addWidget(label)
    set_link_text(label, '<a href="https://b.example">B</a>')
    assert label.text() == '<a href="https://b.example">B</a>'
