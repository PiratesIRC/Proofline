from dataclasses import replace
from types import SimpleNamespace

import pytest
from card_helpers import (
    click_link,
    link_texts,
    option_buttons,
    option_html,
    visible_label_texts,
)
from factories import GatedBackend, finish, release_backends, snapshot
from PyQt6.QtCore import QRect

from proofline import rephrase
from proofline.ai_client import (
    AUTH_MESSAGE,
    REFUSAL_MESSAGE,
    TIMEOUT_MESSAGE,
    AiError,
)
from proofline.ai_service import OFF_MESSAGE, AiService
from proofline.config import Config
from proofline.issue_card import CANCEL_TEXT, CLOSE_TEXT, RETRY_TEXT, IssueCard
from proofline.rephrase import (
    CANCELLED_BUSY_MESSAGE,
    CARET_UNKNOWN_MESSAGE,
    NO_OPTIONS_MESSAGE,
    SENTENCE_TOO_LONG_MESSAGE,
    Rephraser,
    RephraseTarget,
)
from proofline.text_snapshot import ScreenRect

TEXT = "Hi. Me and him goes. Bye."  # sentence at 4..20


@pytest.fixture
def make(qtbot, tmp_path):
    backends = []

    def build(*answers, config=None, key="sk-ant-x"):
        cfg = {"value": config or Config(ai_enabled=True)}
        backend, card, held, replaced = GatedBackend(*answers), IssueCard(), [], []
        backends.append(backend)
        qtbot.addWidget(card)
        service = AiService(lambda: cfg["value"], lambda spec, k, address: backend, lambda pid: key, tmp_path / "ai_usage.jsonl")
        rephraser = Rephraser(service, card, held.append, replaced.append)
        snap = snapshot(text=TEXT)
        target = RephraseTarget(snap, 4, 20, QRect(50, 10, 30, 20), QRect(0, 0, 1920, 1040), "#2e7d32")
        return SimpleNamespace(backend=backend, card=card, held=held, replaced=replaced, service=service,
                               rephraser=rephraser, snap=snap, target=target, cfg=cfg)
    yield build
    release_backends(backends)


def test_start_shows_waiting_then_options(qtbot, make):
    r = make({"options": ["He and I go."]})
    r.rephraser.start(r.target)
    assert r.card.isVisible() and r.held == [True] and r.rephraser.active
    finish(qtbot, r)
    assert [option_html(b) for b in option_buttons(r.card)] == ["<b>He</b> and <b>I go.</b>"]
    assert r.backend.sent[0].text == "Me and him goes."


def test_choosing_an_option_replaces_only_the_sentence(qtbot, make):
    r = make({"options": ["He and I go."]})
    r.rephraser.start(r.target)
    finish(qtbot, r)
    option_buttons(r.card)[0].click()
    (request,) = r.replaced
    assert (request.offset, request.length, request.error_text, request.replacement) == (
        4, 16, "Me and him goes.", "He and I go.")
    assert (request.field_id, request.window_title, request.text) == (r.snap.field_id, r.snap.window_title, TEXT)
    assert r.held == [True, False] and not r.rephraser.active


def test_answer_for_changed_text_is_dropped(qtbot, make):
    r = make({"options": ["He and I go."]})
    r.rephraser.start(r.target)
    r.rephraser.on_field_changed(snapshot(text=TEXT + " More"))
    assert r.card.isHidden() and r.held == [True, False]
    finish(qtbot, r)
    assert r.card.isHidden() and r.replaced == []


def test_focus_leaving_ends_the_rephrase(make):
    r = make({"options": ["x."]})
    r.rephraser.start(r.target)
    r.rephraser.on_field_changed(None)
    assert r.card.isHidden() and not r.rephraser.active


def test_caret_move_keeps_the_rephrase(make):
    r = make({"options": ["x."]})
    r.rephraser.start(r.target)
    r.rephraser.on_field_changed(snapshot(text=TEXT, caret_rect=ScreenRect(5, 5, 6, 20)))
    assert r.card.isVisible() and r.rephraser.active


def test_answer_after_ai_turned_off_is_dropped(qtbot, make):
    r = make({"options": ["He and I go."]})
    r.rephraser.start(r.target)
    r.cfg["value"] = Config(ai_enabled=False)
    finish(qtbot, r)
    assert r.card.isHidden() and not r.rephraser.active and r.replaced == []


def test_late_answer_after_cancel_is_ignored(qtbot, make):
    r = make({"options": ["First answer."]})
    r.rephraser.start(r.target)
    click_link(r.card, CANCEL_TEXT)
    r.rephraser.start(r.target)  # same sentence again (another flagged word in it): the two
    # AiRequests are ==, so only an `is` check drops the late answer
    assert CANCELLED_BUSY_MESSAGE in visible_label_texts(r.card) and RETRY_TEXT in link_texts(r.card)
    finish(qtbot, r)
    assert option_buttons(r.card) == [] and CANCELLED_BUSY_MESSAGE in visible_label_texts(r.card)


def test_no_usable_options_says_so(qtbot, make):
    r = make({"options": ["Me and him goes."]})
    r.rephraser.start(r.target)
    finish(qtbot, r)
    assert NO_OPTIONS_MESSAGE in visible_label_texts(r.card) and RETRY_TEXT not in link_texts(r.card)


def test_timeout_offers_retry_and_retry_sends_again(qtbot, make):
    r = make(AiError("timeout", TIMEOUT_MESSAGE), {"options": ["He and I go."]})
    r.rephraser.start(r.target)
    finish(qtbot, r, "failed")
    assert TIMEOUT_MESSAGE in visible_label_texts(r.card)
    r.backend.gate.clear()
    click_link(r.card, RETRY_TEXT)
    finish(qtbot, r)
    assert len(r.backend.sent) == 2 and len(option_buttons(r.card)) == 1


@pytest.mark.parametrize("error", [AiError("auth", AUTH_MESSAGE), AiError("refusal", REFUSAL_MESSAGE, 5, 0)])
def test_failures_that_would_fail_again_offer_no_retry(qtbot, make, error):
    r = make(error)
    r.rephraser.start(r.target)
    finish(qtbot, r, "failed")
    assert RETRY_TEXT not in link_texts(r.card) and CLOSE_TEXT in link_texts(r.card)


def test_ai_off_sends_nothing(make):
    r = make(config=Config())
    r.rephraser.start(r.target)
    assert OFF_MESSAGE in visible_label_texts(r.card) and RETRY_TEXT not in link_texts(r.card)
    assert r.backend.sent == []


def test_too_long_sentence_gets_the_rephrase_wording(make):
    r = make()
    long_text = "a" * 8001 + "."
    r.rephraser.start(RephraseTarget(snapshot(text=long_text), 0, len(long_text), r.target.anchor,
                                     r.target.bounds, "#2e7d32"))
    assert SENTENCE_TOO_LONG_MESSAGE in visible_label_texts(r.card) and r.backend.sent == []


def test_close_after_a_message_releases_the_card(make):
    r = make(config=Config())
    r.rephraser.start(r.target)
    click_link(r.card, CLOSE_TEXT)
    assert r.held == [True, False] and not r.rephraser.active


def test_target_sentence_is_the_span(make):
    r = make()
    assert r.target.sentence == "Me and him goes."
    assert replace(r.target, start=21, end=25).sentence == "Bye."


def _show_caret_message(r):
    r.rephraser.show_message_at(QRect(0, 0, 0, 0), QRect(0, 0, 1920, 1040), "#2e7d32", CARET_UNKNOWN_MESSAGE,
                                r.snap)


def test_show_message_at_holds_the_card_and_close_releases_it(make):
    r = make()
    _show_caret_message(r)
    assert r.card.isVisible() and CARET_UNKNOWN_MESSAGE in visible_label_texts(r.card) and r.backend.sent == []
    click_link(r.card, CLOSE_TEXT)
    assert r.held == [True, False]


def test_caret_message_closes_when_focus_leaves(make):
    r = make()
    _show_caret_message(r)
    r.rephraser.on_field_changed(None)
    assert r.card.isHidden() and r.held == [True, False]


def test_caret_message_closes_in_another_field(make):
    r = make()
    _show_caret_message(r)
    r.rephraser.on_field_changed(snapshot(field_id=(99,)))
    assert r.card.isHidden() and not r.rephraser.active


def test_caret_message_stays_while_typing_in_the_same_field(make):
    r = make()
    _show_caret_message(r)
    r.rephraser.on_field_changed(replace(r.snap, text=TEXT + " more"))
    assert r.card.isVisible() and r.rephraser.active


def test_start_and_refusal_are_logged_without_the_text(make, caplog):
    r = make(config=Config())
    with caplog.at_level("INFO"):
        r.rephraser.start(r.target)
    text = caplog.text
    assert "Rephrase requested (16 characters)" in text and "AI request refused (rephrase, off)" in text
    assert "Me and him" not in text


def test_credit_is_not_retried():
    """Out of credit will not clear by retrying, so the card must not offer Retry for it."""
    assert "credit" not in rephrase.RETRY_KINDS
