from datetime import datetime

import pytest

from proofline.ai_client import AiError, AiResult
from proofline.ai_service import AiService
from proofline.ai_settings_page import AiPage
from proofline.ai_setup import (
    KEY_WORKS_MESSAGE,
    PASTE_FIRST_MESSAGE,
    AiSetup,
    key_test_request,
)
from proofline.ai_usage import read_entries
from proofline.config import Config


class Keys:
    """Stands in for ai_keys: one key in memory."""

    def __init__(self, key=None):
        self.key = key

    def save(self, key):
        if not key.strip():
            raise ValueError("empty")
        self.key = key.strip()

    def load(self):
        return self.key

    def delete(self):
        self.key = None


class Backend:
    def __init__(self, error=None):
        self.error, self.sent = error, []

    def send(self, request, model):
        self.sent.append(request)
        if self.error:
            raise self.error
        return AiResult({"ok": True}, 30, 5)


@pytest.fixture
def make(qtbot, tmp_path):
    def build(key=None, error=None, config=None):
        keys, backend = Keys(key), Backend(error)
        page = AiPage()
        qtbot.addWidget(page)
        page.load(config or Config(ai_enabled=True))
        page.show()
        service = AiService(lambda: config or Config(ai_enabled=True), lambda k: backend, keys.load,
                            tmp_path / "ai_usage.jsonl", lambda: datetime(2026, 10, 26, 12))
        setup = AiSetup(page, service, keys.save, keys.delete, keys.load)
        return page, keys, backend, setup, tmp_path / "ai_usage.jsonl"
    return build


def test_page_starts_with_the_saved_state(make):
    page, *_ = make(key="sk-ant-saved")
    assert page.key_saved_label.isVisible()
    page, *_ = make()
    assert page.key_box.isVisible()


def test_save_stores_the_key_and_hides_it(make):
    page, keys, *_ = make()
    page.key_box.setText("sk-ant-new")
    page.save_button.click()
    assert keys.key == "sk-ant-new"
    assert page.key_box.isHidden() and page.key_box.text() == ""


def test_saving_an_empty_key_says_so(make):
    page, keys, *_ = make()
    page.key_box.setText("   ")
    page.save_button.click()
    assert keys.key is None
    assert page.key_status.text() == PASTE_FIRST_MESSAGE == "Paste a key first."


def test_remove_deletes_the_key(make):
    page, keys, *_ = make(key="sk-ant-saved")
    page.remove_button.click()
    assert keys.key is None
    assert page.key_box.isVisible()


def test_test_button_sends_one_small_request_and_reports_success(qtbot, make):
    page, _keys, backend, setup, ledger = make(key="sk-ant-saved")
    with qtbot.waitSignal(setup.service.finished):
        page.test_button.click()
    assert backend.sent == [key_test_request()]
    assert key_test_request().max_tokens == 50 and key_test_request().job == "test"
    assert page.key_status.text() == KEY_WORKS_MESSAGE == "The key works."
    assert page.test_button.isEnabled()
    assert len(read_entries(ledger)) == 1
    assert "1 request" in page.usage_label.text()


def test_test_failure_shows_the_message(qtbot, make):
    page, *_, setup, _ = make(key="sk-ant-bad", error=AiError("auth", "The Claude API did not accept the API key."))
    with qtbot.waitSignal(setup.service.failed):
        page.test_button.click()
    assert page.key_status.text() == "The Claude API did not accept the API key."
    assert page.test_button.isEnabled()


def test_test_while_ai_is_off_explains_why(make):
    page, *_ = make(key="sk-ant-saved", config=Config())
    page.test_button.click()
    assert page.key_status.text() == "AI is turned off in Settings."
    assert page.test_button.isEnabled()


def test_showing_the_page_refreshes_the_totals(make):
    page, *_ = make()
    page.hide()
    page.usage_label.setText("")
    page.show()
    assert page.usage_label.text().startswith("Today $0.0000")


def test_save_and_remove_refresh_ai_availability(make):
    page, _keys, _backend, setup, _ledger = make()
    assert not setup.service.available()
    page.key_box.setText("sk-ant-new")
    page.save_button.click()
    assert setup.service.available()
    page.remove_button.click()
    assert not setup.service.available()
