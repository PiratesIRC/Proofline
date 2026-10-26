from datetime import datetime
from types import SimpleNamespace

import pytest
from card_helpers import click_link, link_texts, visible_label_texts
from factories import GatedBackend, finish, issue, release_backends, snapshot
from PyQt6.QtCore import QRect

from proofline.ai_client import TIMEOUT_MESSAGE, AiError
from proofline.ai_find import (
    NOTHING_FOUND_MESSAGE,
    TEXT_TOO_LONG_MESSAGE,
    WAITING_TEXT,
    IssueFinder,
)
from proofline.ai_service import CAP_MESSAGE, AiService
from proofline.ai_usage import UsageEntry, record
from proofline.config import Config
from proofline.overlay_widgets import AI_CANCEL_TEXT, AI_RETRY_TEXT, IssuesPopup
from proofline.rephrase import CANCELLED_BUSY_MESSAGE

ANCHOR = QRect(1500, 900, 20, 20)
BOUNDS = QRect(0, 0, 1920, 1040)


@pytest.fixture
def make(qtbot, tmp_path):
    backends = []

    def build(*answers, config=None):
        cfg = {"value": config or Config(ai_enabled=True)}
        backend, popup, delivered = GatedBackend(*answers), IssuesPopup(), []
        backends.append(backend)
        qtbot.addWidget(popup)
        popup.show_issues((), "Notepad", ANCHOR, BOUNDS, ai_available=True)
        service = AiService(lambda: cfg["value"], lambda spec, key, address: backend, lambda pid: "sk-ant-x", tmp_path / "ai_usage.jsonl")
        finder = IssueFinder(service, popup, lambda snap, matches: delivered.append((snap, matches)))
        return SimpleNamespace(finder=finder, popup=popup, delivered=delivered, snap=snapshot(text="This are a test."),
                               service=service, backend=backend, cfg=cfg, ledger=tmp_path / "ai_usage.jsonl")
    yield build
    release_backends(backends)


def test_start_shows_progress_then_delivers_matches(qtbot, make):
    r = make({"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    assert WAITING_TEXT in visible_label_texts(r.popup) and AI_CANCEL_TEXT in link_texts(r.popup)
    assert r.finder.active
    finish(qtbot, r)
    ((snap, matches),) = r.delivered
    assert snap is r.snap and [(m.error_text, m.offset, m.replacements) for m in matches] == [("are", 5, ("is",))]
    assert WAITING_TEXT not in visible_label_texts(r.popup) and not r.finder.active
    assert r.backend.sent[0].text == "This are a test."


def test_nothing_found_says_so(qtbot, make):
    r = make({"issues": []})
    r.finder.start(r.snap)
    finish(qtbot, r)
    assert NOTHING_FOUND_MESSAGE in visible_label_texts(r.popup) and r.delivered == []


def test_answer_for_changed_text_is_dropped(qtbot, make):
    r = make({"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    assert WAITING_TEXT in visible_label_texts(r.popup)
    r.finder.on_field_changed(snapshot(text="This are a test. More"))
    assert WAITING_TEXT not in visible_label_texts(r.popup)
    finish(qtbot, r)
    assert r.delivered == []


def test_caret_move_keeps_the_request(qtbot, make):
    r = make({"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    r.finder.on_field_changed(snapshot(text="This are a test.", caret_rect=None))
    finish(qtbot, r)
    assert len(r.delivered) == 1


def test_cancel_drops_the_answer_and_clears_the_status(qtbot, make):
    r = make({"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    click_link(r.popup, AI_CANCEL_TEXT)
    assert WAITING_TEXT not in visible_label_texts(r.popup)
    finish(qtbot, r)
    assert r.delivered == [] and visible_label_texts(r.popup).count(NOTHING_FOUND_MESSAGE) == 0


def test_busy_after_cancel_says_the_cancelled_request_is_finishing(qtbot, make):
    r = make({"issues": []})
    r.finder.start(r.snap)
    click_link(r.popup, AI_CANCEL_TEXT)
    r.finder.start(r.snap)  # the cancelled request is still out
    assert CANCELLED_BUSY_MESSAGE in visible_label_texts(r.popup) and AI_RETRY_TEXT in link_texts(r.popup)
    finish(qtbot, r)
    assert r.delivered == []


def test_cap_refusal_offers_no_retry(make):
    r = make(config=Config(ai_enabled=True, ai_monthly_cap_cents=10, ai_model="claude-opus-5-5"))
    record(UsageEntry(datetime.now(), "test", "claude-opus-5-5", 0, 0, 0.09, False), r.ledger)
    r.finder.start(r.snap)  # $0.09 spent; this request's worst case on Opus passes the $0.10 limit
    assert CAP_MESSAGE in visible_label_texts(r.popup) and AI_RETRY_TEXT not in link_texts(r.popup)
    assert r.backend.sent == []


def test_too_long_text_gets_its_own_wording(make):
    r = make()
    r.finder.start(snapshot(text="a" * 8001))
    assert TEXT_TOO_LONG_MESSAGE in visible_label_texts(r.popup) and r.backend.sent == []


def test_timeout_offers_retry_and_retry_sends_again(qtbot, make):
    r = make(AiError("timeout", TIMEOUT_MESSAGE), {"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    finish(qtbot, r, "failed")
    assert TIMEOUT_MESSAGE in visible_label_texts(r.popup)
    r.backend.gate.clear()
    click_link(r.popup, AI_RETRY_TEXT)
    finish(qtbot, r)
    assert len(r.backend.sent) == 2 and len(r.delivered) == 1


def test_status_comes_back_when_the_popup_reopens(qtbot, make):
    r = make({"issues": []})
    r.finder.start(r.snap)
    r.popup.hide()
    r.popup.show_issues((), "Notepad", ANCHOR, BOUNDS, ai_available=True)
    assert WAITING_TEXT in visible_label_texts(r.popup) and AI_CANCEL_TEXT in link_texts(r.popup)
    finish(qtbot, r)  # no request may be left waiting when the test ends


def test_answer_after_ai_turned_off_is_dropped(qtbot, make):
    r = make({"issues": [issue("are", replacement="is")]})
    r.finder.start(r.snap)
    r.cfg["value"] = Config(ai_enabled=False)
    finish(qtbot, r)
    assert r.delivered == [] and WAITING_TEXT not in visible_label_texts(r.popup)
