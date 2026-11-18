"""The badge goes back to where it was dragged, per text box (OverlayController + IssuesPopup)."""

from dataclasses import replace

import pytest
from card_helpers import click_link, link_texts
from drag_helpers import move, press, release
from factories import snapshot
from PyQt6.QtCore import QPoint, QRect

from proofline.badge import BadgeWidget
from proofline.badge_placement import (
    SavedSpot,
    encode,
    field_key,
    lookup,
    place,
    spot_for,
)
from proofline.config import Config
from proofline.lt_client import Match
from proofline.overlay_controller import OverlayController, badge_position
from proofline.overlay_widgets import IssuesPopup
from proofline.screen_coords import ScreenInfo
from proofline.text_snapshot import ScreenRect

MATCH = Match(5, 3, "Did you mean 'is'?", "Grammar", ("is", "was"), "RULE", "Grammar", "are")
SCREENS = (
    ScreenInfo(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040), 1.0),
    ScreenInfo(QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1040), 1.5),
)
FIELD = QRect(0, 0, 400, 200)  # BASE_SNAPSHOT's field_rect on the 100% primary screen
RESET_TEXT = "Reset badge position"
SECRET = "test-secret"
AREAS = tuple(screen.available for screen in SCREENS)


def key(snap):
    return field_key(snap, SECRET)


class Spots:
    def __init__(self, qtbot, config=None, screens=SCREENS):
        self.config = config or Config()
        self.badge = BadgeWidget(primary_button_down=lambda: True)
        self.popup = IssuesPopup()
        qtbot.addWidget(self.badge)
        qtbot.addWidget(self.popup)
        self.controller = OverlayController(lambda: self.config, self.badge, self.popup, lambda: screens,
                                            position_secret=lambda: SECRET)
        self.emitted = []
        self.controller.badge_positions_changed.connect(self.emitted.append)

    def show(self, snap=None, matches=(MATCH,)):
        snap = snap or snapshot()
        self.controller.on_field_changed(snap)
        self.controller.on_checked(snap, matches)
        return snap

    def save(self, snap, spot):
        self.config = replace(self.config, badge_positions=(encode(key(snap), spot),))
        self.controller.on_config_changed()

    def start_drag(self, to=None):
        to = to if to is not None else QPoint(-200, -100)
        start = self.badge.pos() + QPoint(10, 10)
        press(self.badge, start)
        move(self.badge, start + to)
        return start + to

    def finish_drag(self, at):
        release(self.badge, at)


@pytest.fixture
def spots(qtbot):
    return Spots(qtbot)


def test_saved_spot_replaces_automatic_position(spots):
    snap = spots.show()
    spots.save(snap, SavedSpot("br", -100, -50))
    assert spots.badge.pos() == FIELD.bottomRight() + QPoint(-100, -50)


def test_no_saved_spot_uses_badge_position(spots):
    snap = spots.show()
    assert spots.badge.pos() == badge_position(snap, SCREENS)


def test_spot_is_per_box(spots):
    to = spots.show(snapshot(automation_id="to"))
    spots.save(to, SavedSpot("tl", 5, 5))
    assert spots.badge.pos() == QPoint(5, 5)
    cc = spots.show(snapshot(automation_id="cc", field_id=(43, 1)))
    assert spots.badge.pos() == badge_position(cc, SCREENS)


def test_drop_emits_new_positions(spots):
    snap = spots.show()
    at = spots.start_drag()
    dropped = spots.badge.pos()  # after release the harness config is unchanged, so refresh moves it back
    spots.finish_drag(at)
    assert len(spots.emitted) == 1
    assert lookup(spots.emitted[0], key(snap)) == spot_for(dropped, FIELD)


def test_drop_is_clamped_on_screen_before_saving(spots):
    snap = spots.show()
    at = spots.start_drag(to=QPoint(-5000, -5000))
    spots.finish_drag(at)
    saved = lookup(spots.emitted[0], key(snap))
    assert saved == SavedSpot("tl", 0, 0)  # the badge cannot sit left of or above the screen


def test_drop_after_focus_change_is_discarded(spots):
    spots.show()
    at = spots.start_drag()
    spots.controller.on_field_changed(snapshot(field_id=(99, 9)))
    spots.finish_drag(at)
    assert spots.emitted == []


def test_refresh_during_drag_does_not_move_badge(spots):
    snap = spots.show()
    spots.start_drag()
    dragged_to = spots.badge.pos()
    spots.controller.on_field_changed(replace(snap, caret_rect=ScreenRect(50, 50, 51, 70),
                                              field_rect=ScreenRect(500, 500, 900, 700)))
    assert spots.badge.pos() == dragged_to


def test_clean_result_during_drag_does_not_hide_badge(qtbot):
    s = Spots(qtbot, Config(badge_always_visible=False))
    snap = s.show()
    at = s.start_drag()
    s.controller.on_checked(snap, ())
    assert s.badge.isVisible()
    s.finish_drag(at)
    assert not s.badge.isVisible()


def test_field_lost_during_drag_hides_after_release(spots):
    spots.show()
    at = spots.start_drag()
    spots.controller.on_field_changed(None)
    assert spots.badge.isVisible()
    spots.finish_drag(at)
    assert not spots.badge.isVisible()
    assert spots.emitted == []


def test_saved_spot_for_field_off_every_screen_falls_back(spots):
    snap = snapshot(field_rect=ScreenRect(9000, 100, 9400, 300))
    spots.show(snap)
    spots.save(snap, SavedSpot("br", -10, -10))
    assert spots.badge.pos() == badge_position(snap, SCREENS)


def test_drag_start_hides_unpinned_popup(spots):
    spots.show()
    spots.badge.clicked.emit()
    assert spots.popup.isVisible()
    spots.start_drag()
    assert not spots.popup.isVisible()


def test_reset_link_shown_only_with_saved_spot(spots):
    snap = spots.show()
    spots.badge.clicked.emit()
    spots.popup._more_button.click()
    assert RESET_TEXT not in link_texts(spots.popup)
    spots.popup.hide()
    spots.save(snap, SavedSpot("br", -10, -10))
    spots.badge.clicked.emit()
    spots.popup._more_button.click()  # hiding the popup closed More
    assert RESET_TEXT in link_texts(spots.popup)


def test_reset_link_removes_spot(spots):
    snap = spots.show()
    spots.save(snap, SavedSpot("br", -10, -10))
    spots.badge.clicked.emit()
    spots.popup._more_button.click()
    click_link(spots.popup, RESET_TEXT)
    assert len(spots.emitted) == 1
    assert lookup(spots.emitted[0], key(snap)) is None
    assert not spots.popup.isVisible()


def test_no_screens_falls_back_to_automatic_position(qtbot):
    s = Spots(qtbot, screens=())
    snap = s.show()
    s.save(snap, SavedSpot("br", -10, -10))
    assert s.badge.pos() == badge_position(snap, ())


def test_spot_saved_with_another_secret_is_not_found(spots):
    snap = spots.show()
    spots.config = replace(spots.config, badge_positions=(encode(field_key(snap, "other"), SavedSpot("tl", 5, 5)),))
    spots.controller.on_config_changed()
    assert spots.badge.pos() == badge_position(snap, SCREENS)


def test_spot_can_sit_on_another_screen(spots):
    snap = spots.show()
    spots.save(snap, SavedSpot("tr", 1700, 50))  # FIELD's topRight is (399, 0)
    assert spots.badge.pos() == QPoint(2099, 50)


def test_drop_on_another_screen_is_kept(spots):
    snap = spots.show()
    at = spots.start_drag(to=QPoint(1800, 100))
    dropped = spots.badge.pos()
    assert dropped.x() > 1920  # really on the second screen
    spots.finish_drag(at)
    saved = lookup(spots.emitted[0], key(snap))
    assert place(saved, FIELD, AREAS, SCREENS[0].available) == dropped


def test_tiny_field_uses_saved_spot(spots):
    tiny = snapshot(field_rect=ScreenRect(100, 100, 140, 120))  # 40 x 20: too small for the automatic spot
    spots.show(tiny)
    spots.save(tiny, SavedSpot("br", 20, 20))
    assert spots.badge.pos() == QPoint(139 + 20, 119 + 20)


def test_drop_on_tiny_field_is_saved(spots):
    tiny = snapshot(field_rect=ScreenRect(100, 100, 140, 120))
    spots.show(tiny)
    at = spots.start_drag(to=QPoint(300, 0))
    spots.finish_drag(at)
    assert lookup(spots.emitted[0], key(tiny)) is not None


def test_badge_stays_put_while_pressed(spots):
    snap = spots.show()
    before = spots.badge.pos()
    start = before + QPoint(10, 10)
    press(spots.badge, start)
    spots.controller.on_field_changed(replace(snap, field_rect=ScreenRect(500, 500, 900, 700)))
    assert spots.badge.pos() == before  # a caret poll must not move it out from under the mouse
    release(spots.badge, start)
    spots.controller.refresh()
    assert spots.badge.pos() != before
