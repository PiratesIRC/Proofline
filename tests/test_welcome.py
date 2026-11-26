from dataclasses import replace

import pytest
from PyQt6.QtWidgets import QLabel

from proofline import welcome as welcome_module
from proofline.config import DEFAULT_SERVER_URL, Config, validate
from proofline.server_test import READY
from proofline.welcome import (
    AI_BUTTON_TEXT,
    AI_FEATURES_TEXT,
    AI_LIMIT_TEXT,
    AI_OFF_TEXT,
    PAGE_COUNT,
    WelcomeWindow,
    should_show_welcome,
)


class Store:
    def __init__(self):
        self.config = validate(Config())
        self.saves = []

    def save(self, config):
        self.config = validate(config)
        self.saves.append(self.config)
        return self.config


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def window(qtbot, store, monkeypatch):
    monkeypatch.setattr(welcome_module, "run_server_test", lambda url, language: READY)
    w = WelcomeWindow(lambda: store.config, store.save)
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def window_with_ai(qtbot, store, monkeypatch):
    monkeypatch.setattr(welcome_module, "run_server_test", lambda url, language: READY)
    calls = []
    w = WelcomeWindow(lambda: store.config, store.save, open_ai_settings=lambda: calls.append("ai"))
    qtbot.addWidget(w)
    w.show()
    w.calls = calls
    return w


def test_only_a_fresh_install_sees_the_welcome():
    assert should_show_welcome(Config(), config_existed=False)
    assert not should_show_welcome(Config(), config_existed=True)  # upgrading users skip it
    assert not should_show_welcome(Config(welcome_shown=True), config_existed=False)


def test_pages_step_forward_and_back(window):
    assert window.page_index() == 0 and not window.back_button.isEnabled()
    window.next_button.click()
    assert window.page_index() == 1
    window.back_button.click()
    assert window.page_index() == 0
    for _ in range(PAGE_COUNT - 1):
        window.next_button.click()
    assert window.page_index() == PAGE_COUNT - 1 and window.next_button.text() == "Finish"


def test_there_are_four_pages_and_the_ai_page_sits_before_the_done_page(window):
    assert PAGE_COUNT == 4
    headings = [window._pages.widget(i).findChild(QLabel, "welcomeHeading").text() for i in range(PAGE_COUNT)]
    assert headings == [
        "Connect to your LanguageTool server", "How it works", "AI suggestions (optional)", "You are all set",
    ]


def test_ai_page_says_nothing_is_sent_unless_turned_on(window):
    window.next_button.click()
    window.next_button.click()
    texts = [label.text() for label in window._pages.currentWidget().findChildren(QLabel)]
    assert AI_OFF_TEXT in texts


def test_ai_page_describes_the_features_provider_and_spending_limit():
    text = " ".join(AI_FEATURES_TEXT.split())
    for phrase in ("rephrase a sentence", "find more issues", "correctly spelled words used in the wrong place",
                   "rewrite for clarity", "change tone"):
        assert phrase in text
    assert "Claude is the default" in welcome_module.AI_PROVIDER_TEXT
    assert "$1.00" in AI_LIMIT_TEXT


def test_ai_button_calls_the_callback_and_stays_on_the_ai_page(window_with_ai):
    window = window_with_ai
    window.next_button.click()
    window.next_button.click()
    assert window.ai_button.isEnabled() and window.ai_button.text() == AI_BUTTON_TEXT
    window.ai_button.click()
    assert window.calls == ["ai"]
    assert window.page_index() == 2


def test_ai_button_is_not_usable_without_a_callback(window):
    window.next_button.click()
    window.next_button.click()
    assert not window.ai_button.isEnabled()


def test_next_skips_the_ai_page(window):
    window.next_button.click()
    window.next_button.click()
    window.next_button.click()
    assert window.page_index() == 3 and window.next_button.text() == "Finish"


def test_closing_from_the_ai_page_marks_it_shown(window, store):
    window.next_button.click()
    window.next_button.click()
    window.close()
    assert store.config.welcome_shown


def test_finish_saves_server_startup_and_marks_shown(window, store):
    window.other_server.setChecked(True)
    window.url_edit.setText("https://lt.example")
    window.next_button.click()
    window.next_button.click()
    window.next_button.click()
    window.autostart.setChecked(True)
    window.next_button.click()
    saved = store.config
    assert (saved.server_url, saved.start_with_windows, saved.welcome_shown) == (
        "https://lt.example/v2/check", True, True)
    assert not window.isVisible()


def test_this_pc_uses_the_default_server_and_tests_it(qtbot, window):
    assert window.server_url() == DEFAULT_SERVER_URL
    window.test_button.click()
    qtbot.waitUntil(lambda: "Ready" in window.status.text())


def test_another_server_uses_the_typed_address(window):
    window.other_server.setChecked(True)
    window.url_edit.setText("https://lt.example")
    assert window.server_url() == "https://lt.example"


def test_closing_early_still_marks_it_shown(window, store):
    window.close()
    assert store.config.welcome_shown
    assert store.config.server_url == DEFAULT_SERVER_URL  # nothing else changed


def test_invalid_address_keeps_the_window_open(window, store):
    window.other_server.setChecked(True)
    window.url_edit.setText("not a url")
    for _ in range(3):
        window.next_button.click()
    assert window.isVisible() and window.page_index() == 0
    assert "Address not valid" in window.status.text()
    assert store.config == replace(store.config, welcome_shown=False)


def test_plain_http_to_another_computer_warns_and_asks(window, store):
    window.other_server.setChecked(True)
    window.url_edit.setText("http://lan-server:8010")
    assert window.insecure_bar.isVisibleTo(window)
    asked = []
    window.confirm_insecure = lambda url: asked.append(url) or False
    window.next_button.click()
    assert asked == ["http://lan-server:8010/v2/check"] and window.page_index() == 0
    window.confirm_insecure = lambda url: True
    window.next_button.click()
    assert window.page_index() == 1


def test_https_and_this_pc_do_not_warn(window):
    assert not window.insecure_bar.isVisibleTo(window)
    window.other_server.setChecked(True)
    window.url_edit.setText("https://lt.example")
    assert not window.insecure_bar.isVisibleTo(window)
