"""Underlines hide while the text scrolls and come back where the words settle."""

import time

from factories import focus_result, snapshot

from proofline.config import Config
from proofline.lt_client import Match
from proofline.text_monitor import SCROLL_SETTLE_S, TextMonitor
from proofline.text_snapshot import ScreenRect
from proofline.underlines import Underlines, target_for

FIELD = ScreenRect(0, 0, 400, 200)
ARE = Match(5, 3, "msg", "", ("is",), "RULE", "Grammar", "are")
POLL_S = 0.05


class Page:
    """The flagged word's vertical position; tests change it to simulate scrolling."""

    def __init__(self):
        self.top = 10
        self.anchor_calls = 0

    def rects(self, target):
        word = ScreenRect(50, self.top, 80, self.top + 20)
        return Underlines(target.field_id, target.text, FIELD, ((word,),), target.spans)

    def anchor(self, _target):
        self.anchor_calls += 1
        return self.top


def _monitor(page, anchor_reader=None):
    snap = snapshot()
    monitor = TextMonitor(Config(debounce_ms=200), reader=lambda: focus_result(snap),
                          replacer=lambda _r: None, poll_interval_s=POLL_S, rect_reader=page.rects,
                          anchor_reader=anchor_reader or page.anchor)
    monitor.set_underline_target(target_for(snap, (ARE,)))
    return monitor


def test_lines_hide_when_the_word_moves_and_return_at_its_new_place(qtbot):
    page, seen = Page(), []
    monitor = _monitor(page)
    monitor.underlines_changed.connect(seen.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: len(seen) == 1 and page.anchor_calls >= 2, timeout=2000)
        assert seen[0].rects[0][0].top == 10
        page.top = 300  # the page scrolled
        qtbot.waitUntil(lambda: len(seen) >= 2, timeout=2000)
        assert seen[1] is None  # hidden as soon as the move is seen
        hidden_at = time.monotonic()
        qtbot.waitUntil(lambda: len(seen) >= 3, timeout=3000)
        assert time.monotonic() - hidden_at >= SCROLL_SETTLE_S * 0.8  # waited for the word to settle
        assert seen[2].rects[0][0].top == 300  # drawn at the new place
    finally:
        monitor.stop()


def test_lines_stay_while_the_word_does_not_move(qtbot):
    page, seen = Page(), []
    monitor = _monitor(page)
    monitor.underlines_changed.connect(seen.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: len(seen) == 1, timeout=2000)
        qtbot.waitUntil(lambda: page.anchor_calls >= 8, timeout=3000)
        assert len(seen) == 1  # no hide, no redraw
    finally:
        monitor.stop()


def test_lines_stay_hidden_while_the_word_keeps_moving(qtbot):
    page, seen = Page(), []

    def scrolling(_target):
        page.anchor_calls += 1
        if 3 <= page.anchor_calls < 15:  # a long scroll: a new position on every check
            page.top += 5
        return page.top

    monitor = _monitor(page, anchor_reader=scrolling)
    monitor.underlines_changed.connect(seen.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: len(seen) >= 2, timeout=3000)
        assert seen[1] is None
        qtbot.waitUntil(lambda: page.anchor_calls >= 10, timeout=3000)
        assert len(seen) == 2  # still hidden mid-scroll
        qtbot.waitUntil(lambda: len(seen) >= 3, timeout=3000)
        assert seen[2] is not None and page.anchor_calls >= 15
    finally:
        monitor.stop()


def test_moving_is_reported_when_the_field_moves_without_underlines(qtbot):
    page, moves, lines = Page(), [], []
    snap = snapshot()
    monitor = TextMonitor(Config(debounce_ms=200), reader=lambda: focus_result(snap),
                          replacer=lambda _r: None, poll_interval_s=POLL_S, anchor_reader=page.anchor)
    monitor.moving.connect(moves.append)
    monitor.underlines_changed.connect(lines.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: page.anchor_calls >= 3, timeout=2000)
        page.top = 250  # the badge's field scrolled; there are no underlines to hide
        qtbot.waitUntil(lambda: moves == [True, False], timeout=3000)
        assert lines == []
    finally:
        monitor.stop()


def test_overlay_hides_badge_and_lines_while_moving_and_restores_them(qtbot):
    from test_underlines import Harness, measured

    h = Harness(qtbot)
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    h.controller.on_underlines(measured(h.targets[-1]))
    assert h.badge.isVisible() and h.lines.isVisible()
    h.controller.on_moving(True)
    assert not h.badge.isVisible() and not h.lines.isVisible()
    h.controller.refresh()  # anything that refreshes mid-scroll must not bring the badge back
    assert not h.badge.isVisible()
    h.controller.on_moving(False)
    assert h.badge.isVisible()


def test_a_failing_anchor_reader_leaves_the_lines_alone(qtbot):
    page, seen, calls = Page(), [], []

    def broken(_target):
        calls.append(1)
        raise RuntimeError("element vanished")

    monitor = _monitor(page, anchor_reader=broken)
    monitor.underlines_changed.connect(seen.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: len(seen) == 1 and len(calls) >= 6, timeout=3000)
        assert len(seen) == 1
    finally:
        monitor.stop()
