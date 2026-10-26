from dataclasses import replace

import pytest
from factories import focus_result, snapshot
from PyQt6.QtCore import QRect, Qt

from proofline.badge import BadgeWidget
from proofline.config import Config
from proofline.lt_client import Match
from proofline.overlay_controller import OverlayController
from proofline.overlay_widgets import IssuesPopup
from proofline.screen_coords import ScreenInfo
from proofline.text_monitor import TextMonitor
from proofline.text_snapshot import ScreenRect
from proofline.underline_overlay import UnderlineOverlay, wave_path
from proofline.underlines import (
    MAX_UNDERLINES,
    Span,
    Underlines,
    UnderlineTarget,
    clean_rects,
    target_for,
)

FIELD = ScreenRect(0, 0, 400, 200)
SCREENS = (ScreenInfo(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040), 1.0),)
ARE = Match(5, 3, "msg", "", ("is",), "RULE", "Grammar", "are")
TEST = Match(11, 4, "msg", "", ("text",), "RULE", "Grammar", "test")
WORD = ScreenRect(50, 10, 80, 30)


@pytest.mark.parametrize(
    ("rect", "expected"),
    [
        (WORD, (WORD,)),
        (ScreenRect(385, 198, 386, 222), ()),  # Edge: 1 px wide, before a line start
        (ScreenRect(275, 199, 300, 200), ()),  # Edge: scrolled out, pinned to the bottom edge
        (ScreenRect(390, 50, 420, 70), (ScreenRect(390, 50, 400, 70),)),  # runs past the right edge
        (ScreenRect(10, 300, 40, 320), ()),  # below the field
    ],
)
def test_clean_rects_clips_to_field_and_drops_slivers(rect, expected):
    assert clean_rects([rect], FIELD) == expected


def test_target_lists_spans_in_text_order():
    target = target_for(snapshot(), (TEST, ARE))
    assert target.spans == (Span(5, 3, "are"), Span(11, 4, "test"))
    assert target.applies_to(snapshot())
    assert not target.applies_to(snapshot(text="This is a test."))
    assert not target.applies_to(None)


def test_target_skips_empty_matches_and_caps_the_count():
    assert target_for(snapshot(), (replace(ARE, length=0),)) is None
    assert target_for(None, (ARE,)) is None
    many = [replace(ARE, offset=i) for i in range(MAX_UNDERLINES + 5)]
    assert len(target_for(snapshot(), many).spans) == MAX_UNDERLINES


def measured(target, rects=((WORD,),)):
    return Underlines(target.field_id, target.text, FIELD, rects)


def test_monitor_measures_only_while_the_text_matches(qtbot):
    target = target_for(snapshot(), (ARE,))
    reader_result = {"value": focus_result(snapshot())}
    monitor = TextMonitor(Config(debounce_ms=200), reader=lambda: reader_result["value"],
                          replacer=lambda _r: None, poll_interval_s=0.01, rect_reader=measured)
    try:
        with qtbot.waitSignal(monitor.underlines_changed, timeout=2000) as blocker:
            monitor.set_underline_target(target)
            monitor.start()
        assert blocker.args[0] == measured(target)
        with qtbot.waitSignal(monitor.underlines_changed, timeout=2000) as blocker:
            reader_result["value"] = focus_result(snapshot(text="This are a test!"))
        assert blocker.args[0] is None
    finally:
        monitor.stop()


def test_monitor_survives_a_failing_rect_reader(qtbot):
    def broken(_target):
        raise RuntimeError("element vanished")

    snap = snapshot()
    monitor = TextMonitor(Config(), reader=lambda: focus_result(snap), replacer=lambda _r: None,
                          poll_interval_s=0.01, rect_reader=broken)
    monitor.set_underline_target(target_for(snap, (ARE,)))
    try:
        with qtbot.waitSignal(monitor.text_ready, timeout=3000):
            monitor.start()
    finally:
        monitor.stop()


class Harness:
    def __init__(self, qtbot, config=None):
        self.config = config or Config()
        self.badge, self.popup, self.lines = BadgeWidget(), IssuesPopup(), UnderlineOverlay()
        for widget in (self.badge, self.popup, self.lines):
            qtbot.addWidget(widget)
        self.controller = OverlayController(lambda: self.config, self.badge, self.popup, lambda: SCREENS,
                                            underlines=self.lines)
        self.targets = []
        self.controller.underline_target_changed.connect(self.targets.append)


def test_controller_asks_for_underlines_and_draws_them(qtbot):
    h = Harness(qtbot)
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    target = h.targets[-1]
    assert target == target_for(snap, (ARE,))
    h.controller.on_underlines(measured(target))
    assert h.lines.isVisible()
    assert h.lines.geometry() == QRect(0, 0, 400, 200)
    assert h.lines.rects == (QRect(50, 10, 30, 20),)


def test_controller_hides_underlines_when_the_text_changes(qtbot):
    h = Harness(qtbot)
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    h.controller.on_underlines(measured(h.targets[-1]))
    h.controller.on_field_changed(snapshot(text="This are a test!"))
    assert h.targets[-1] is None
    assert not h.lines.isVisible()


def test_controller_ignores_measurements_for_an_old_target(qtbot):
    h = Harness(qtbot)
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    stale = UnderlineTarget(snap.field_id, "older text", (Span(0, 3, "old"),))
    h.controller.on_underlines(measured(stale))
    assert not h.lines.isVisible()


def test_setting_off_sends_no_target(qtbot):
    h = Harness(qtbot, Config(show_underlines=False))
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    assert all(target is None for target in h.targets)


def test_overlay_lets_clicks_through(qtbot):
    lines = UnderlineOverlay()
    qtbot.addWidget(lines)
    assert lines.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_wave_stays_inside_the_word_rectangle():
    rect = QRect(10, 10, 30, 20)
    bounds = wave_path(rect).boundingRect()
    assert bounds.top() >= rect.top() and bounds.bottom() <= rect.bottom() + 1
    assert bounds.left() == rect.left() and bounds.right() >= rect.right()
