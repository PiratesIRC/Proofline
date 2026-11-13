"""The overlay windows never take focus from the text field the user is typing in.

The design depends on Windows never activating the badge, the popup, the issue card or the
underline overlay, so these tests read the native window's extended style bits.
"""

from __future__ import annotations

import ctypes

import pytest
from PyQt6.QtWidgets import QWidget

from proofline.badge import BadgeWidget
from proofline.issue_card import IssueCard
from proofline.non_activating import (
    GWL_EXSTYLE,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    make_non_activating,
)
from proofline.overlay_widgets import IssuesPopup
from proofline.underline_overlay import UnderlineOverlay

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


def _ex_style(widget: QWidget) -> int:
    return ctypes.windll.user32.GetWindowLongW(int(widget.winId()), GWL_EXSTYLE)


def test_a_plain_window_has_none_of_the_bits(qapp) -> None:
    # Control: proves the reading below would see a window without the setup.
    widget = QWidget()
    assert _ex_style(widget) & (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) == 0
    widget.deleteLater()


def test_setup_marks_the_window_never_activated_and_off_the_taskbar(qapp) -> None:
    widget = QWidget()
    make_non_activating(widget)
    style = _ex_style(widget)
    assert style & WS_EX_NOACTIVATE
    assert style & WS_EX_TOOLWINDOW
    # Layered: transparent areas render see-through instead of black.
    assert style & WS_EX_LAYERED
    widget.deleteLater()


@pytest.mark.parametrize("make", [BadgeWidget, IssuesPopup, IssueCard, UnderlineOverlay],
                         ids=["badge", "popup", "issue card", "underlines"])
def test_every_overlay_window_is_never_activated(qapp, make) -> None:
    widget = make()
    assert _ex_style(widget) & WS_EX_NOACTIVATE
    widget.deleteLater()


def test_only_the_underlines_let_clicks_through(qapp) -> None:
    lines, popup = UnderlineOverlay(), IssuesPopup()
    assert _ex_style(lines) & WS_EX_TRANSPARENT
    assert not _ex_style(popup) & WS_EX_TRANSPARENT
    lines.deleteLater()
    popup.deleteLater()
