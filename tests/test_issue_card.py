from dataclasses import replace

import pytest
from card_helpers import (
    click_link,
    link_texts,
    option_buttons,
    option_html,
    visible_label_texts,
)
from factories import issue_match, snapshot
from PyQt6.QtCore import QRect

from proofline.ai_jobs import is_ai_match
from proofline.badge import BadgeState, BadgeWidget
from proofline.config import Config
from proofline.issue_card import (
    CANCEL_TEXT,
    CARD_GAP,
    CLOSE_TEXT,
    REPHRASE_TEXT,
    RETRY_TEXT,
    SENTENCE_PREVIEW_CHARS,
    WAITING_TEXT,
    IssueCard,
    card_position,
)
from proofline.lt_client import Match
from proofline.overlay_controller import OverlayController
from proofline.overlay_widgets import AI_TEXT, IssuesPopup
from proofline.rephrase import RephraseTarget
from proofline.replace_request import ReplaceRequest
from proofline.screen_coords import ScreenInfo
from proofline.text_snapshot import ScreenRect
from proofline.underline_overlay import UnderlineOverlay
from proofline.underlines import Underlines, span_at, target_for

SCREENS = (ScreenInfo(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040), 1.0),)
FIELD = ScreenRect(0, 0, 400, 200)
ARE_RECT = ScreenRect(50, 10, 80, 30)
ARE = Match(5, 3, "Did you mean 'is'?", "Grammar", ("is", "was"), "RULE", "Grammar", "are")
TEST = Match(11, 4, "Possible spelling mistake.", "Spelling", ("text",), "MORFOLOGIK_RULE_EN_US",
             "Possible Typo", "test", "TYPOS")
TEST_RECT = ScreenRect(120, 10, 160, 30)


def caret_at(x):
    return ScreenRect(x, 12, x + 1, 28)


def measured(snap):
    return Underlines(snap.field_id, snap.text, FIELD, ((ARE_RECT,), (TEST_RECT,)), target_for(snap, (TEST, ARE)).spans)


@pytest.mark.parametrize(("x", "expected"), [(50, 0), (65, 0), (79, None), (80, None), (130, 1), (10, None)])
def test_span_at_counts_the_caret_inside_a_word_but_not_just_after_it(x, expected):
    found = span_at(measured(snapshot()), caret_at(x))
    assert (found[0] if found else None) == expected


def test_span_at_needs_the_caret_on_the_same_line():
    assert span_at(measured(snapshot()), ScreenRect(60, 40, 61, 56)) is None


def test_card_sits_below_the_word_or_above_it_at_the_screen_bottom():
    bounds = QRect(0, 0, 1920, 1040)
    size = QRect(0, 0, 260, 120)
    assert card_position(QRect(100, 100, 60, 20), size, bounds).y() == 120 + CARD_GAP
    above = card_position(QRect(100, 1000, 60, 20), size, bounds)
    assert above.y() == 1000 - CARD_GAP - 120
    assert card_position(QRect(1900, 100, 60, 20), size, bounds).x() == 1920 - 260


class Harness:
    def __init__(self, qtbot, config=None, ai_available=lambda: True):
        self.badge, self.popup, self.lines, self.card = BadgeWidget(), IssuesPopup(), UnderlineOverlay(), IssueCard()
        for widget in (self.badge, self.popup, self.lines, self.card):
            qtbot.addWidget(widget)
        self.config = config or Config()
        self.controller = OverlayController(lambda: self.config, self.badge, self.popup, lambda: SCREENS,
                                            underlines=self.lines, card=self.card, ai_available=ai_available)
        self.requests = []
        self.rephrase: list[RephraseTarget] = []
        self.controller.rephrase_requested.connect(self.rephrase.append)
        self.controller.replace_requested.connect(self.requests.append)
        self.snap = snapshot()
        self.controller.on_field_changed(self.snap)
        self.controller.on_checked(self.snap, (TEST, ARE))
        self.controller.on_underlines(measured(self.snap))

    def move_caret(self, x):
        self.snap = snapshot(caret_rect=caret_at(x))
        self.controller.on_field_changed(self.snap)


@pytest.fixture
def harness(qtbot):
    return Harness(qtbot)


def test_card_follows_the_caret_into_and_out_of_flagged_words(harness):
    assert harness.card.match is None  # the factory caret (x=10) is in no word
    harness.move_caret(60)
    assert harness.card.match == ARE
    assert harness.card.geometry().top() == 30 + CARD_GAP
    harness.move_caret(130)
    assert harness.card.match == TEST
    harness.move_caret(300)
    assert harness.card.match is None


def test_first_suggestion_on_the_card_applies_it(harness):
    harness.move_caret(60)
    harness.card._choose("is")
    assert not harness.card.isVisible()
    assert harness.requests[-1].replacement == "is"
    assert harness.requests[-1].error_text == "are"


def test_all_issues_opens_the_popup_and_hides_the_card(harness):
    harness.move_caret(60)
    harness.card._open_all()
    assert harness.popup.isVisible()
    assert not harness.card.isVisible()
    harness.move_caret(65)  # the card stays away while the popup lists everything
    assert not harness.card.isVisible()


def test_ignore_on_the_card_drops_the_issue(harness):
    harness.move_caret(60)
    harness.card._emit_and_hide(harness.card.ignore_requested)
    assert harness.badge._count == 1


def test_typing_hides_the_card(harness):
    harness.move_caret(60)
    harness.controller.on_field_changed(snapshot(text="This are a test!", caret_rect=caret_at(60)))
    assert not harness.card.isVisible()


def test_card_shrinks_for_an_issue_with_fewer_fixes(qtbot):
    card = IssueCard()
    qtbot.addWidget(card)
    many = Match(0, 7, "msg", "Spelling", ("one", "two", "three"), "R", "Typo", "mistaks")
    card.show_for(many, QRect(100, 100, 60, 20), QRect(0, 0, 1920, 1040))
    tall = card.height()
    card.show_for(ARE, QRect(100, 100, 60, 20), QRect(0, 0, 1920, 1040))
    assert card.height() < tall


WORD = QRect(50, 10, 30, 20)
BOUNDS = QRect(0, 0, 1920, 1040)


@pytest.fixture
def card(qtbot):
    widget = IssueCard()
    qtbot.addWidget(widget)
    return widget


def test_rephrase_link_only_when_ai_is_available(card):
    card.show_for(ARE, WORD, BOUNDS)
    assert REPHRASE_TEXT not in link_texts(card)
    card.show_for(ARE, WORD, BOUNDS, ai_available=True)
    assert REPHRASE_TEXT in link_texts(card)


def test_rephrase_link_emits_the_match_and_keeps_the_card(qtbot, card):
    card.show_for(ARE, WORD, BOUNDS, ai_available=True)
    with qtbot.waitSignal(card.rephrase_requested) as blocker:
        click_link(card, REPHRASE_TEXT)
    assert blocker.args == [ARE] and card.isVisible()


def test_waiting_shows_the_sentence_progress_and_cancel(qtbot, card):
    card.show_waiting("Me and him goes.", WORD, BOUNDS, "#2e7d32")
    texts = visible_label_texts(card)
    assert card.isVisible() and WAITING_TEXT in texts and "Me and him goes." in texts
    assert card.match is None
    with qtbot.waitSignal(card.rephrase_cancelled):
        click_link(card, CANCEL_TEXT)
    assert card.isHidden()


def test_long_sentence_is_shortened_in_the_card(card):
    sentence = "word " * 40
    card.show_waiting(sentence, WORD, BOUNDS, "#2e7d32")
    shown = [t for t in visible_label_texts(card) if t.startswith("word")]
    assert len(shown) == 1 and len(shown[0]) == SENTENCE_PREVIEW_CHARS and shown[0].endswith("\u2026")


def test_options_show_bold_changes_and_emit_the_choice(qtbot, card):
    card.show_waiting("Me and him goes.", WORD, BOUNDS, "#2e7d32")
    card.show_options(("He and I go.", "We go."), "Me and him goes.")
    buttons = option_buttons(card)
    assert len(buttons) == 2 and "<b>He</b>" in option_html(buttons[0])
    with qtbot.waitSignal(card.rephrase_chosen) as blocker:
        buttons[1].click()
    assert blocker.args == ["We go."] and card.isHidden()


def test_message_offers_retry_only_when_asked(qtbot, card):
    card.show_waiting("s.", WORD, BOUNDS, "#2e7d32")
    card.show_message("Could not reach the Claude API.", retry=True)
    with qtbot.waitSignal(card.rephrase_retry):
        click_link(card, RETRY_TEXT)
    card.show_message("Monthly AI limit reached.", retry=False)
    assert RETRY_TEXT not in link_texts(card) and CLOSE_TEXT in link_texts(card)
    with qtbot.waitSignal(card.rephrase_cancelled):
        click_link(card, CLOSE_TEXT)
    assert card.isHidden()


def test_message_can_open_the_card_by_itself(card):
    card.show_message("Proofline can't find the caret in this field.", retry=False,
                      anchor=WORD, bounds=BOUNDS, accent="#2e7d32")
    assert card.isVisible() and card.geometry().top() == WORD.bottom() + 1 + CARD_GAP


def test_states_show_a_hidden_card_again(card):
    card.show_waiting("s.", WORD, BOUNDS, "#2e7d32")
    card.hide()
    card.show_options(("t.",), "s.")
    assert card.isVisible()


def test_card_flipped_above_the_word_grows_upward(card):
    low = QRect(50, 1000, 30, 20)
    card.show_waiting("s.", low, BOUNDS, "#2e7d32")
    card.show_options(("A much longer wording that wraps over several lines in the card.",) * 3, "s.")
    assert card.geometry().bottom() < low.top()


def test_flagged_word_card_returns_after_a_rephrase(card):
    card.show_for(ARE, WORD, BOUNDS, ai_available=True)
    card.show_waiting("s.", WORD, BOUNDS, "#2e7d32")
    card.show_for(ARE, WORD, BOUNDS, ai_available=True)
    assert card.match == ARE and REPHRASE_TEXT in link_texts(card)


def test_card_offers_rephrase_when_ai_is_available(harness):
    harness.move_caret(60)
    assert REPHRASE_TEXT in link_texts(harness.card)


def test_rephrase_link_emits_the_flagged_sentence(harness):
    harness.move_caret(60)
    click_link(harness.card, REPHRASE_TEXT)
    (target,) = harness.rephrase
    assert target.sentence == "This are a test." and (target.start, target.end) == (0, 16)
    assert target.anchor == QRect(50, 10, 30, 20)
    assert harness.card.isVisible()


def test_held_card_survives_hides(harness):
    harness.move_caret(60)
    harness.controller.hold_card(True)
    harness.card.show_waiting("s.", QRect(50, 10, 30, 20), QRect(0, 0, 1920, 1040), "#2e7d32")
    harness.move_caret(300)  # caret leaves the word
    harness.controller.on_underlines(None)  # failed re-measure
    harness.controller.on_checked(harness.snap, ())  # recheck clears the target
    assert harness.card.isVisible()
    harness.controller.hold_card(False)
    assert harness.card.isHidden()  # release refreshes: no word at the caret


def test_blank_sentence_gives_no_target(harness):
    assert harness.controller.rephrase_target(snapshot(text="One.\n\nTwo."), 5, None) is None


def test_target_without_a_caret_opens_at_the_field_corner(harness):
    target = harness.controller.rephrase_target(snapshot(field_rect=ScreenRect(100, 200, 500, 400)), 3, None)
    assert (target.anchor.left(), target.anchor.top()) == (100, 200)


def test_choosing_a_wording_goes_through_the_checked_replace(harness):
    harness.move_caret(60)
    request = ReplaceRequest(harness.snap.field_id, "", harness.snap.text, 5, 3, "are", "is")
    harness.controller.request_replace(request)
    assert harness.requests == [request]


def test_option_button_is_measured_at_its_real_width(card):
    from proofline.issue_card import OPTION_BUTTON_WIDTH

    card.show_waiting("s.", WORD, BOUNDS, "#2e7d32")
    card.show_options(("He and I go to the shop every morning before work.",), "s.")
    (button,) = option_buttons(card)
    assert button.width() == OPTION_BUTTON_WIDTH


def test_no_link_is_squeezed_when_ai_adds_rephrase(card):
    from PyQt6.QtWidgets import QPushButton

    card.show_for(TEST, WORD, BOUNDS, ai_available=True)  # spelling: Ignore, Add to dictionary, Rephrase, All issues
    links = [b for b in card.findChildren(QPushButton, "linkButton") if b.isVisible()]
    assert len(links) == 4
    assert all(b.width() >= b.sizeHint().width() for b in links), [(b.text(), b.width(), b.sizeHint().width())
                                                                   for b in links]


def test_rephrase_says_it_uses_ai():
    assert REPHRASE_TEXT == "AI Rephrase"


def test_card_text_is_plain(card):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    card.show_for(replace(ARE, message="<b>x</b>", replacements=()), WORD, BOUNDS)
    labels = [label for label in card.findChildren(QLabel) if label.text() == "<b>x</b>"]
    assert labels and all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)


def _ai_matches(harness):
    return [m for m in harness.controller._matches if is_ai_match(m)]


def test_ai_matches_join_languagetool_matches(harness):
    ai_this, ai_test = issue_match("This", offset=0), issue_match("test", offset=11)
    harness.controller.set_ai_matches(harness.snap, (ai_this, ai_test))
    assert _ai_matches(harness) == [ai_this]  # "test" overlaps LanguageTool's TEST
    assert TEST in harness.controller._matches and ARE in harness.controller._matches


def test_recheck_keeps_ai_matches(harness):
    ai_this = issue_match("This", offset=0)
    harness.controller.set_ai_matches(harness.snap, (ai_this,))
    harness.controller.on_checked(harness.snap, (TEST,))
    assert _ai_matches(harness) == [ai_this]


def test_ai_matches_belong_to_their_field(harness):
    harness.controller.set_ai_matches(snapshot(field_id=(99,)), (issue_match("This", offset=0),))
    assert _ai_matches(harness) == []


def test_ai_matches_clear_when_text_changes_but_move_with_our_own_fix(harness):
    ai_this = issue_match("This", offset=0)
    ai_test = issue_match("test", offset=11)
    harness.controller.set_ai_matches(harness.snap, (ai_this, ai_test))
    harness.controller.request_replace(ReplaceRequest(harness.snap.field_id, "", harness.snap.text, 5, 3, "are", "is"))
    moved = snapshot(text="This is a test.")
    harness.controller.on_field_changed(moved)
    harness.controller.on_checked(moved, ())
    ai_now = _ai_matches(harness)
    assert [(m.error_text, m.offset) for m in ai_now] == [("This", 0), ("test", 10)]  # after the edit: shifted by -1
    harness.controller.on_field_changed(snapshot(text="Typed something else."))
    assert _ai_matches(harness) == []


def test_a_replace_that_did_not_happen_clears_ai_matches(harness):
    ai_this = issue_match("This", offset=0)
    harness.controller.set_ai_matches(harness.snap, (ai_this,))
    harness.controller.request_replace(ReplaceRequest(harness.snap.field_id, "", harness.snap.text, 5, 3, "are", "is"))
    typed = snapshot(text="This was a test.")  # not the expected result; "This" still matches its slice
    harness.controller.on_field_changed(typed)
    harness.controller.on_checked(typed, ())
    assert _ai_matches(harness) == []


def test_ignore_and_disabled_rules_with_ai_matches(qtbot):
    h = Harness(qtbot, config=Config(disabled_rules=("AI_SUGGESTION",)))
    ai_this = issue_match("This", offset=0)
    h.controller.set_ai_matches(h.snap, (ai_this,))
    assert ai_this in h.controller._matches  # disabled rules never hide AI findings
    h.controller._on_ignore(ai_this)
    assert ai_this not in h.controller._matches


def test_dictionary_words_are_not_ai_findings(qtbot):
    h = Harness(qtbot, config=Config(personal_dictionary=("this",)))
    h.controller.set_ai_matches(h.snap, (issue_match("This", offset=0),))
    assert _ai_matches(h) == []


def test_badge_goes_clean_to_issues_and_back(harness):
    harness.controller.on_checked(harness.snap, ())
    assert harness.controller._state is BadgeState.CLEAN
    ai_this = issue_match("This", offset=0)
    harness.controller.set_ai_matches(harness.snap, (ai_this,))
    assert harness.controller._state is BadgeState.ISSUES and harness.controller._matches == (ai_this,)
    harness.controller._on_ignore(ai_this)
    assert harness.controller._state is BadgeState.CLEAN


def test_answer_during_a_check_keeps_the_spinner(harness):
    typed = snapshot(text="This are a test now.")
    harness.controller.on_field_changed(typed)
    harness.controller.set_ai_matches(typed, (issue_match("This", offset=0),))
    assert harness.controller._state is BadgeState.CHECKING
    harness.controller.on_checked(typed, ())
    assert len(_ai_matches(harness)) == 1


def test_find_more_without_a_field_emits_nothing(qtbot, harness):
    seen = []
    harness.controller.find_more_requested.connect(seen.append)
    harness.popup.find_more_requested.emit()
    assert seen == [harness.snap]
    harness.controller.on_field_changed(None)
    harness.popup.find_more_requested.emit()
    assert seen == [harness.snap]


def test_stale_measurement_is_not_used(harness):
    old = measured(harness.snap)  # measured for LanguageTool's two spans
    harness.controller.set_ai_matches(harness.snap, (issue_match("This", offset=0),))
    harness.controller.on_underlines(old)
    harness.move_caret(60)
    assert harness.card.match is None and harness.controller._measured is None


def test_wrapped_span_keeps_its_colour(harness):
    harness.controller.set_ai_matches(harness.snap, (issue_match("This", offset=0),))
    spans = harness.controller._target.spans  # This, are, test
    wrapped = (ScreenRect(0, 10, 20, 30), ScreenRect(0, 40, 10, 60))
    harness.controller.on_underlines(Underlines(harness.snap.field_id, harness.snap.text, FIELD,
                                                (wrapped, (ARE_RECT,), (TEST_RECT,)), spans))
    assert harness.lines.ai_flags == (True, True, False, False)


def test_popup_offers_ai_on_a_clean_field(harness):
    harness.controller.on_checked(harness.snap, ())
    harness.controller._show_popup()
    assert AI_TEXT in link_texts(harness.popup)


def test_card_tooltip_shows_quotes_and_ampersands_as_typed(card):
    from PyQt6.QtCore import Qt as QtNs
    from PyQt6.QtGui import QTextDocument
    from PyQt6.QtWidgets import QPushButton

    card.show_for(replace(ARE, message='Don\'t use "their" & co.'), WORD, BOUNDS)
    tip = card.findChildren(QPushButton, "cardFirstFix")[0].toolTip()
    assert QtNs.mightBeRichText(tip)  # so Qt decodes the escaped characters
    document = QTextDocument()
    document.setHtml(tip)
    assert document.toPlainText() == 'Don\'t use "their" & co.'


def test_popup_hides_ai_while_the_server_is_unreachable(harness):
    harness.controller.on_check_failed("Could not reach the server.")
    harness.controller._show_popup()
    assert AI_TEXT not in link_texts(harness.popup)
