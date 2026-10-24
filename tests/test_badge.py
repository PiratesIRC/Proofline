import math

import pytest
from PyQt6.QtGui import QColor, QImage, QPainter

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
