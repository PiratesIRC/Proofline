from dataclasses import replace

import pytest
from card_helpers import click_link, link_texts, visible_label_texts
from factories import snapshot
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QLabel, QWidget

from proofline.badge import BADGE_SIZE, BadgeState, BadgeWidget
from proofline.config import Config
from proofline.lt_client import Match
from proofline.overlay_controller import (
    CHECKING_STATUS,
    OverlayController,
    badge_position,
)
from proofline.overlay_widgets import (
    AI_CANCEL_TEXT,
    AI_RETRY_TEXT,
    AI_TEXT,
    DISABLE_RULE_TEXT,
    FIND_MORE_TEXT,
    POPUP_MAX_HEIGHT,
    IssuesPopup,
    _popup_position,
    issue_count_text,
    match_excerpt,
)
from proofline.screen_coords import ScreenInfo, to_logical_rect
from proofline.text_snapshot import ScreenRect

MATCH = Match(5, 3, "Did you mean 'is'?", "Grammar", ("is", "was"), "RULE", "Grammar", "are")
# Primary 1920x1080 at 100%, secondary to the right at 150% (2880x1620 physical).
SCREENS = (
    ScreenInfo(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040), 1.0),
    ScreenInfo(QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1040), 1.5),
)


def test_logical_rect_on_scaled_secondary_screen():
    rect = to_logical_rect(ScreenRect(1920 + 300, 150, 1920 + 600, 450), SCREENS)
    assert rect == QRect(1920 + 200, 100, 200, 200)


def test_logical_rect_on_unscaled_primary_is_unchanged():
    assert to_logical_rect(ScreenRect(10, 20, 110, 70), SCREENS) == QRect(10, 20, 100, 50)


def test_badge_sits_inside_bottom_right_of_field():
    snap = snapshot(field_rect=ScreenRect(100, 100, 500, 300))
    assert badge_position(snap, SCREENS) == QPoint(499 - BADGE_SIZE - 4, 299 - BADGE_SIZE - 4)


def test_single_line_badge_sits_outside_right_edge_so_site_icons_stay_visible():
    snap = snapshot(field_rect=ScreenRect(100, 100, 500, 132))  # e.g. a search box
    pos = badge_position(snap, SCREENS)
    assert pos.x() == 499 + 4  # beyond the field's right edge
    assert pos.y() == QRect(100, 100, 400, 32).center().y() - BADGE_SIZE // 2


def test_single_line_badge_falls_back_inside_at_screen_edge():
    snap = snapshot(field_rect=ScreenRect(1500, 100, 1920, 132))  # touches the right screen edge
    pos = badge_position(snap, SCREENS)
    assert pos.x() + BADGE_SIZE <= 1919


def test_badge_clipped_to_visible_screen_area():
    snap = snapshot(field_rect=ScreenRect(100, 100, 500, 5000))  # extends below taskbar
    assert badge_position(snap, SCREENS).y() == 1039 - BADGE_SIZE - 4


def test_badge_falls_back_to_caret_for_tiny_field():
    snap = snapshot(field_rect=ScreenRect(100, 100, 120, 120), caret_rect=ScreenRect(300, 300, 301, 320))
    assert badge_position(snap, SCREENS) == QPoint(300 + 4, 319 - BADGE_SIZE)


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (QRect(800, 500, 24, 24), QPoint(823 - 300, 500 - 200 - 4)),  # above, right-aligned
        (QRect(800, 50, 24, 24), QPoint(823 - 300, 73 + 4)),  # no room above: below
        (QRect(100, 500, 24, 24), QPoint(0, 296)),  # clamped to the left edge
    ],
)
def test_popup_position(anchor, expected):
    assert _popup_position(anchor, 300, 200, QRect(0, 0, 1920, 1040)) == expected


class Harness:
    def __init__(self, qtbot, config=None):
        self.config = config or Config()
        self.badge = BadgeWidget()
        self.popup = IssuesPopup()
        qtbot.addWidget(self.badge)
        qtbot.addWidget(self.popup)
        self.controller = OverlayController(lambda: self.config, self.badge, self.popup, lambda: SCREENS)


@pytest.fixture
def harness(qtbot):
    return Harness(qtbot)


def test_focus_shows_checking_badge_then_issue_count(harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    assert harness.badge.isVisible()
    assert harness.badge.state is BadgeState.CHECKING
    harness.controller.on_checked(snap, (MATCH,))
    assert harness.badge.state is BadgeState.ISSUES
    assert harness.badge._count == 1


def test_badge_hidden_while_clean_when_not_always_visible(qtbot):
    h = Harness(qtbot, Config(badge_always_visible=False))
    snap = snapshot()
    h.controller.on_field_changed(snap)
    assert not h.badge.isVisible()
    h.controller.on_checked(snap, ())
    assert not h.badge.isVisible()
    h.controller.on_checked(snap, (MATCH,))
    assert h.badge.isVisible()


def test_stale_results_are_ignored(harness):
    harness.controller.on_field_changed(snapshot(text="new text"))
    harness.controller.on_checked(snapshot(text="old text"), (MATCH,))
    assert harness.badge.state is BadgeState.CHECKING


def test_typing_resets_to_checking_and_hides_popup(harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.badge.clicked.emit()
    assert harness.popup.isVisible()
    harness.controller.on_field_changed(replace(snap, text=snap.text + "x"))
    assert not harness.popup.isVisible()
    assert harness.badge.state is BadgeState.CHECKING


def test_caret_move_keeps_results(harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.controller.on_field_changed(replace(snap, caret_rect=ScreenRect(50, 10, 51, 30)))
    assert harness.badge.state is BadgeState.ISSUES


def test_focus_leaving_text_hides_everything(harness):
    harness.controller.on_field_changed(snapshot())
    harness.controller.on_field_changed(None)
    assert not harness.badge.isVisible()
    assert not harness.popup.isVisible()


def test_check_failure_shows_error_state_with_message(harness):
    harness.controller.on_field_changed(snapshot())
    harness.controller.on_check_failed("Could not connect")
    assert harness.badge.state is BadgeState.ERROR
    assert harness.badge.toolTip() == "Could not connect"


def test_choosing_replacement_emits_request(qtbot, harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.badge.clicked.emit()
    with qtbot.waitSignal(harness.controller.replace_requested) as blocker:
        harness.popup.replacement_chosen.emit(MATCH, "is")
    request = blocker.args[0]
    assert (request.offset, request.length, request.error_text, request.replacement) == (5, 3, "are", "is")
    assert request.field_id == snap.field_id
    assert not harness.popup.isVisible()


def test_disable_buttons_emit_app_and_window(qtbot, harness):
    harness.controller.on_field_changed(snapshot())
    with qtbot.waitSignal(harness.controller.disable_app_requested) as app_signal:
        harness.popup.disable_app_requested.emit()
    assert app_signal.args == ["notepad.exe"]
    assert not harness.badge.isVisible()

    harness.controller.on_field_changed(snapshot())
    with qtbot.waitSignal(harness.controller.disable_window_requested) as window_signal:
        harness.popup.disable_window_requested.emit()
    assert window_signal.args == ["notes.txt - Notepad"]


def test_popup_lists_matches_with_fix_buttons(qtbot, harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.badge.clicked.emit()
    labels = [b.text() for b in harness.popup.findChildren(type(harness.popup._disable_app_button))]
    assert {"is", "was", "Turn off in notepad.exe", "Turn off in this window"} <= set(labels)
    fix = next(b for b in harness.popup.findChildren(type(harness.popup._disable_app_button)) if b.text() == "is")
    with qtbot.waitSignal(harness.popup.replacement_chosen) as blocker:
        fix.click()
    assert blocker.args == [MATCH, "is"]


POPUP_ANCHOR = QRect(1500, 900, 20, 20)
POPUP_BOUNDS = QRect(0, 0, 1920, 1040)


def _visible_rows(popup):
    direct = Qt.FindChildOption.FindDirectChildrenOnly
    return [w for w in popup._list.findChildren(QWidget, options=direct) if w.isVisible()]


def test_open_popup_grows_when_results_update(qtbot):
    popup = IssuesPopup()
    qtbot.addWidget(popup)
    popup.show_issues((), "notepad.exe", POPUP_ANCHOR, POPUP_BOUNDS)
    empty_height = popup.height()

    popup.show_issues((MATCH, MATCH), "notepad.exe", POPUP_ANCHOR, POPUP_BOUNDS)

    rows = _visible_rows(popup)
    assert len(rows) == 2
    assert popup.height() > empty_height
    # The list area is tall enough for every row, so nothing is squashed.
    assert popup._scroll.height() >= sum(row.sizeHint().height() for row in rows)


def test_open_popup_caps_list_height_and_shrinks_back(qtbot):
    popup = IssuesPopup()
    qtbot.addWidget(popup)
    popup.show_issues((MATCH,) * 30, "notepad.exe", POPUP_ANCHOR, POPUP_BOUNDS)
    assert popup._scroll.height() == POPUP_MAX_HEIGHT

    popup.show_issues((), "notepad.exe", POPUP_ANCHOR, POPUP_BOUNDS)

    assert popup._scroll.height() < POPUP_MAX_HEIGHT
    assert [row.text() for row in _visible_rows(popup)] == ["No issues found."]


def test_match_excerpt_marks_flagged_words_in_context():
    match = Match(5, 3, "", "", ("is",), "R", "Grammar", "are")
    assert match_excerpt("This are a test.", match) == ("This ", "are", " a test.")


def test_match_excerpt_cuts_long_text_at_word_edges():
    text = "word " * 20 + "are" + " word" * 20
    start = text.index("are")
    before, flagged, after = match_excerpt(text, Match(start, 3, "", "", (), "R", "", "are"), context=12)
    assert flagged == "are"
    assert before.startswith("…") and after.endswith("…")
    assert len(before) <= 13 and len(after) <= 13


def test_match_excerpt_none_when_text_changed():
    assert match_excerpt("Something else", MATCH) is None


@pytest.mark.parametrize(("count", "text"), [(0, "No issues"), (1, "1 issue"), (3, "3 issues")])
def test_issue_count_text(count, text):
    assert issue_count_text(count) == text


def open_popup(harness, matches=(MATCH,)):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, matches)
    harness.badge.clicked.emit()
    return snap


def test_turn_off_buttons_stay_folded_under_more_options(harness):
    open_popup(harness)
    assert not harness.popup._disable_app_button.isVisible()
    harness.popup._more_button.click()
    assert harness.popup._disable_app_button.isVisible()
    assert harness.popup._header.text() == "1 issue"


def test_popup_uses_friendly_app_name(qtbot):
    h = Harness(qtbot)
    h.controller._app_name_provider = lambda snap: "Notepad"
    open_popup(h)
    assert h.popup._disable_app_button.text() == "Turn off in Notepad"


def test_disabling_a_rule_shows_undo_that_emits(qtbot, harness):
    open_popup(harness)
    harness.popup.disable_rule_requested.emit(MATCH)
    assert "Grammar" in harness.popup.notice_text
    with qtbot.waitSignal(harness.controller.undo_requested) as undo:
        harness.popup._on_undo()
    assert undo.args == ["disabled_rules", "RULE"]
    assert harness.popup.notice_text == ""


def test_disabling_the_app_leaves_only_an_undo_notice(qtbot, harness):
    open_popup(harness)
    harness.popup.disable_app_requested.emit()
    assert harness.popup.is_notice_only
    assert not harness.badge.isVisible()
    harness.controller.on_field_changed(None)  # the monitor now skips the app
    assert harness.popup.isVisible()
    with qtbot.waitSignal(harness.controller.undo_requested) as undo:
        harness.popup._on_undo()
    assert undo.args == ["disabled_apps", "notepad.exe"]
    assert not harness.popup.isVisible()


def test_apply_first_suggestion_fixes_the_first_issue(qtbot, harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    assert not harness.controller.apply_first_suggestion()  # nothing checked yet
    harness.controller.on_checked(snap, (Match(0, 4, "m", "", (), "R0", "", "This"), MATCH))
    with qtbot.waitSignal(harness.controller.replace_requested) as blocker:
        assert harness.controller.apply_first_suggestion()
    assert (blocker.args[0].error_text, blocker.args[0].replacement) == ("are", "is")  # first one with a fix


@pytest.mark.parametrize("text", ["", "   ", "\ufeff", "One"])
def test_no_checking_badge_until_there_is_enough_text_to_check(harness, text):
    harness.controller.on_field_changed(snapshot(text=text))  # min_words defaults to 2
    assert not harness.badge.isVisible()
    harness.controller.on_field_changed(snapshot(text=text + " more words"))
    assert harness.badge.isVisible()
    assert harness.badge.state is BadgeState.CHECKING


def test_explicit_check_of_short_text_still_shows_its_result(harness):
    snap = snapshot(text="Teh")
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))  # Check now ignores the minimum length
    assert harness.badge.isVisible()
    assert harness.badge.state is BadgeState.ISSUES


HEADER_POINT = QPoint(20, 12)  # on the popup's header label
DRAG_BY = QPoint(200, 150)


def drag_popup(qtbot, popup, by=DRAG_BY):
    start = popup.pos() + HEADER_POINT
    qtbot.mousePress(popup, Qt.MouseButton.LeftButton, pos=HEADER_POINT)
    popup.mouseMoveEvent(_mouse_move(popup, start + by))
    qtbot.mouseRelease(popup, Qt.MouseButton.LeftButton, pos=HEADER_POINT)
    return popup.pos()


def _mouse_move(popup, global_pos):
    local = QPointF(popup.mapFromGlobal(global_pos))
    return QMouseEvent(
        QEvent.Type.MouseMove, local, QPointF(global_pos),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def test_dragged_popup_stays_open_through_typing_and_focus_changes(qtbot, harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.badge.clicked.emit()
    before = harness.popup.pos()
    dropped = drag_popup(qtbot, harness.popup)
    assert dropped == before + DRAG_BY
    assert harness.popup.is_pinned

    harness.controller.on_field_changed(replace(snap, text=snap.text + " More"))
    assert harness.popup.isVisible()
    assert harness.popup._header.text() == CHECKING_STATUS
    assert harness.popup._scroll.isHidden()
    harness.controller.on_field_changed(None)
    assert harness.popup.isVisible()

    newer = replace(snap, text="Thsi is new.")
    harness.controller.on_field_changed(newer)
    harness.controller.on_checked(newer, (MATCH,))
    assert not harness.popup._scroll.isHidden()  # results for the new text fill it again
    assert harness.popup.pos() == dropped  # where the user put it
    harness.badge.clicked.emit()
    assert harness.popup.isVisible()  # the badge no longer closes it

    harness.popup.hide()  # what Close does
    assert not harness.popup.is_pinned
    harness.badge.clicked.emit()
    assert harness.popup.pos() != dropped  # next time it opens beside the badge again


def test_short_click_on_popup_does_not_pin_it(qtbot, harness):
    snap = snapshot()
    harness.controller.on_field_changed(snap)
    harness.controller.on_checked(snap, (MATCH,))
    harness.badge.clicked.emit()
    drag_popup(qtbot, harness.popup, by=QPoint(1, 1))
    assert not harness.popup.is_pinned
    harness.controller.on_field_changed(replace(snap, text=snap.text + "x"))
    assert not harness.popup.isVisible()


AI_MATCH = Match(0, 5, "Use have.", "AI suggestion", ("I have",), "AI_SUGGESTION", "AI", "I has", "AI")


@pytest.fixture
def popup(qtbot):
    widget = IssuesPopup()
    qtbot.addWidget(widget)
    return widget


def test_ai_link_only_when_ai_is_available(popup):
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS)
    assert AI_TEXT not in link_texts(popup)
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)
    assert AI_TEXT in link_texts(popup)


def test_ai_link_opens_find_more_issues(qtbot, popup):
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)
    click_link(popup, AI_TEXT)
    with qtbot.waitSignal(popup.find_more_requested):
        click_link(popup, FIND_MORE_TEXT)
    assert FIND_MORE_TEXT not in link_texts(popup)


def test_ai_status_line_offers_cancel_and_retry_and_survives_a_refresh(qtbot, popup):
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)
    popup.show_ai_status("Asking the AI...", cancel=True)
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)  # a recheck
    assert "Asking the AI..." in visible_label_texts(popup)
    with qtbot.waitSignal(popup.ai_cancel_requested):
        click_link(popup, AI_CANCEL_TEXT)
    popup.show_ai_status("Could not reach the Claude API.", retry=True)
    with qtbot.waitSignal(popup.ai_retry_requested):
        click_link(popup, AI_RETRY_TEXT)
    popup.clear_ai_status()
    assert "Could not reach the Claude API." not in visible_label_texts(popup)


def test_ai_parts_follow_popup_modes(popup):
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)
    click_link(popup, AI_TEXT)
    popup.show_ai_status("Asking the AI...", cancel=True)
    popup.show_notice_only("Checking is off in Notepad.", "disabled_apps", "notepad.exe")
    assert AI_TEXT not in link_texts(popup) and FIND_MORE_TEXT not in link_texts(popup)
    assert "Asking the AI..." not in visible_label_texts(popup)
    popup.hide()
    popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, ai_available=True)
    assert FIND_MORE_TEXT not in link_texts(popup) and "Asking the AI..." not in visible_label_texts(popup)


def test_popup_shown_signal_fires_when_it_opens(qtbot, popup):
    with qtbot.waitSignal(popup.shown):
        popup.show_issues((), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS)


def test_ai_rows_offer_no_rule_switch(popup):
    popup.show_issues((AI_MATCH,), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, text="I has a cat.")
    assert "AI suggestion" in visible_label_texts(popup)
    assert DISABLE_RULE_TEXT not in link_texts(popup)


def test_ai_text_is_plain(popup):
    marked = replace(AI_MATCH, message="<b>x</b>")
    popup.show_issues((marked,), "Notepad", POPUP_ANCHOR, POPUP_BOUNDS, text="I has a cat.")
    labels = [label for label in popup.findChildren(QLabel) if label.text() == "<b>x</b>"]
    assert labels and all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)
