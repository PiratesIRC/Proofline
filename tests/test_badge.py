import ctypes
import math

import pytest
from drag_helpers import LEFT, RIGHT, drag, move, press, release
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from proofline.badge import (
    ATTENTION_PULSES,
    BADGE_SIZE,
    POP_MS,
    PULSE_PERIOD_MS,
    BadgeState,
    BadgeWidget,
    animation_duration_ms,
    badge_label,
    pop_scale,
)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance_ms(self, ms):
        self.now += ms / 1000


@pytest.fixture
def make_badge(qtbot):
    def make(animations=True):
        clock = FakeClock()
        badge = BadgeWidget(animations_enabled=lambda: animations, clock=clock)
        qtbot.addWidget(badge)
        badge.show()
        return badge, clock

    return make


def test_durations_and_pop_curve():
    assert animation_duration_ms(BadgeState.CHECKING) == math.inf
    assert animation_duration_ms(BadgeState.ISSUES) == ATTENTION_PULSES * PULSE_PERIOD_MS
    assert animation_duration_ms(BadgeState.ERROR) == 0
    assert pop_scale(0) == 1.0
    assert pop_scale(POP_MS / 2) > 1.1
    assert pop_scale(POP_MS) == 1.0


@pytest.mark.parametrize(("count", "label"), [(3, "3"), (9, "9"), (12, "9+")])
def test_issue_count_label(count, label):
    assert badge_label(BadgeState.ISSUES, count) == label


def test_spinner_runs_while_checking(make_badge):
    badge, clock = make_badge()
    badge.set_state(BadgeState.CHECKING)
    assert badge.is_animating
    clock.advance_ms(60_000)
    badge._on_frame()
    assert badge.is_animating  # keeps spinning until the result arrives


def test_issue_pulses_then_settles_and_replays_when_count_changes(make_badge):
    badge, clock = make_badge()
    badge.set_state(BadgeState.ISSUES, 2)
    assert badge.is_animating
    clock.advance_ms(ATTENTION_PULSES * PULSE_PERIOD_MS + 1)
    badge._on_frame()
    assert not badge.is_animating
    badge.set_state(BadgeState.ISSUES, 2)  # same result: stays calm
    assert not badge.is_animating
    badge.set_state(BadgeState.ISSUES, 3)  # new count: draws attention again
    assert badge.is_animating


def test_clean_pops_once(make_badge):
    badge, clock = make_badge()
    badge.set_state(BadgeState.CLEAN)
    assert badge.is_animating
    clock.advance_ms(POP_MS + 1)
    badge._on_frame()
    assert not badge.is_animating


def test_no_animation_when_windows_animation_effects_are_off(make_badge):
    badge, _ = make_badge(animations=False)
    badge.set_state(BadgeState.CHECKING)
    assert not badge.is_animating


def test_hidden_badge_does_not_animate(make_badge):
    badge, _ = make_badge()
    badge.set_state(BadgeState.CHECKING)
    badge.hide()
    assert not badge.is_animating


def _composite(badge, background):
    image = QImage(BADGE_SIZE, BADGE_SIZE, QImage.Format.Format_ARGB32)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.drawImage(0, 0, badge.grab().toImage())
    painter.end()
    return image


@pytest.mark.parametrize("background", ["#ffffff", "#000000"])
def test_badge_edge_contrasts_with_white_and_black_fields(make_badge, background):
    badge, _ = make_badge(animations=False)
    badge.set_state(BadgeState.CLEAN)
    image = _composite(badge, background)
    bg = QColor(background).lightness()
    # Scan from the left edge toward the centre along the middle row: the edge of the
    # badge must contain a pixel that differs strongly from the field colour.
    row = BADGE_SIZE // 2
    contrasts = [abs(image.pixelColor(x, row).lightness() - bg) for x in range(BADGE_SIZE // 2)]
    assert max(contrasts) > 120


def test_badge_disc_meets_the_24_px_target_size():
    from proofline.badge import DISC_DIAMETER

    assert DISC_DIAMETER >= 24 and BADGE_SIZE > DISC_DIAMETER


def test_badge_has_an_accessible_name_that_follows_its_state(qtbot):
    from proofline.badge import BadgeState, BadgeWidget

    badge = BadgeWidget(animations_enabled=lambda: False)
    qtbot.addWidget(badge)
    badge.set_state(BadgeState.ISSUES, 3)
    assert badge.accessibleName() == "Proofline: 3 issues. Click to see them."
    badge.set_state(BadgeState.CLEAN)
    assert badge.accessibleName() == "Proofline: no issues found"


# ----- dragging ----------------------------------------------------------------


def _record(badge):
    seen = {"clicked": 0, "drag_started": 0, "moved": []}
    badge.clicked.connect(lambda: seen.__setitem__("clicked", seen["clicked"] + 1))
    badge.drag_started.connect(lambda: seen.__setitem__("drag_started", seen["drag_started"] + 1))
    badge.moved.connect(lambda point: seen["moved"].append((point, badge.is_dragging)))
    return seen


def _placed(make_badge):
    badge, _clock = make_badge()
    badge.move(QPoint(300, 300))
    return badge, _record(badge)


def test_press_does_not_emit_clicked(make_badge):
    badge, seen = _placed(make_badge)
    press(badge, QPoint(310, 310))
    assert seen["clicked"] == 0


def test_press_and_release_emits_clicked(make_badge):
    badge, seen = _placed(make_badge)
    press(badge, QPoint(310, 310))
    release(badge, QPoint(310, 310))
    assert seen == {"clicked": 1, "drag_started": 0, "moved": []}


def test_small_movement_is_a_click(make_badge):
    badge, seen = _placed(make_badge)
    d = QApplication.startDragDistance()
    drag(badge, QPoint(310, 310), QPoint(310 + d - 1, 310))
    assert seen == {"clicked": 1, "drag_started": 0, "moved": []}
    assert badge.pos() == QPoint(300, 300)


def test_drag_moves_window_and_emits_moved(make_badge):
    badge, seen = _placed(make_badge)
    press(badge, QPoint(310, 310))
    move(badge, QPoint(370, 340))
    assert badge.is_dragging
    release(badge, QPoint(370, 340))
    assert seen["drag_started"] == 1
    assert badge.pos() == QPoint(360, 330)
    assert seen["moved"] == [(QPoint(360, 330), False)]  # is_dragging already cleared in the slot


def test_drag_does_not_emit_clicked(make_badge):
    badge, seen = _placed(make_badge)
    drag(badge, QPoint(310, 310), QPoint(370, 340))
    assert seen["clicked"] == 0


def test_right_button_does_nothing(make_badge):
    badge, seen = _placed(make_badge)
    d = QApplication.startDragDistance()
    drag(badge, QPoint(310, 310), QPoint(320 + d, 310), button=RIGHT)
    assert seen == {"clicked": 0, "drag_started": 0, "moved": []}
    assert badge.pos() == QPoint(300, 300)


def test_drag_keeps_badge_non_activating(make_badge):
    from proofline.non_activating import WS_EX_NOACTIVATE

    badge, _seen = _placed(make_badge)
    drag(badge, QPoint(310, 310), QPoint(370, 340), button=LEFT)
    assert badge.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert badge.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    style = ctypes.windll.user32.GetWindowLongW(int(badge.winId()), -20)  # GWL_EXSTYLE
    assert style & WS_EX_NOACTIVATE


def _held_badge(qtbot):
    held = {"down": True}
    badge = BadgeWidget(primary_button_down=lambda: held["down"])
    qtbot.addWidget(badge)
    badge.show()
    badge.move(QPoint(300, 300))
    return badge, held, _record(badge)


def test_lost_release_ends_drag_when_button_is_up(qtbot):
    badge, held, seen = _held_badge(qtbot)
    press(badge, QPoint(310, 310))
    move(badge, QPoint(370, 340))
    assert badge.is_dragging
    held["down"] = False  # e.g. Alt+Tab took the mouse away; no release event will come
    badge._watch_drag()
    assert not badge.is_dragging
    assert seen["moved"] == [(QPoint(360, 330), False)]
    assert seen["clicked"] == 0


def test_watch_keeps_drag_while_button_held(qtbot):
    badge, _held, seen = _held_badge(qtbot)
    press(badge, QPoint(310, 310))
    move(badge, QPoint(370, 340))
    badge._watch_drag()
    assert badge.is_dragging
    assert seen["moved"] == []


def test_new_press_clears_a_stuck_drag(qtbot):
    badge, _held, seen = _held_badge(qtbot)
    press(badge, QPoint(310, 310))
    move(badge, QPoint(370, 340))
    press(badge, QPoint(370, 340))  # the release of the first drag never arrived
    assert not badge.is_dragging
    release(badge, QPoint(370, 340))
    assert seen["clicked"] == 1
