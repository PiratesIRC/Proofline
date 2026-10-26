import pytest
from PyQt6.QtCore import Qt

from proofline.ai_settings_page import AiPage
from proofline.ai_usage import Totals
from proofline.config import Config


@pytest.fixture
def page(qtbot):
    p = AiPage()
    qtbot.addWidget(p)
    p.load(Config())
    p.show()
    p.changes = []
    p.changed.connect(p.changes.append)
    return p


def test_load_does_not_emit(qtbot):
    p = AiPage()
    qtbot.addWidget(p)
    seen = []
    p.changed.connect(seen.append)
    p.load(Config(ai_enabled=True, ai_model="claude-opus-5-5", ai_monthly_cap_cents=500))
    assert seen == []
    assert p.cap_box.value() == 5.0
    assert p.model_box.currentData() == "claude-opus-5-5"


def test_switch_model_and_cap_emit_changes(page):
    page.enabled_switch.setChecked(True)
    page.model_box.setCurrentIndex(page.model_box.findData("claude-sonnet-5-5"))
    page.cap_box.setValue(2.5)
    assert page.changes == [{"ai_enabled": True}, {"ai_model": "claude-sonnet-5-5"}, {"ai_monthly_cap_cents": 250}]


def test_model_choices_show_their_prices(page):
    labels = [page.model_box.itemText(i) for i in range(page.model_box.count())]
    assert labels[0] == "Haiku 5.5 ($0.10 / $0.50 per million tokens)"
    assert len(labels) == 3


def test_key_box_never_shows_a_saved_key(page):
    page.key_box.setText("sk-ant-typed")
    page.set_key_saved(True)
    assert page.key_box.isHidden() and page.key_box.text() == ""
    assert page.key_saved_label.isVisible() and page.remove_button.isVisible()
    assert not page.save_button.isVisible()
    page.set_key_saved(False)
    assert page.key_box.isVisible() and not page.remove_button.isVisible()


def test_save_emits_the_typed_key(qtbot, page):
    page.set_key_saved(False)
    page.key_box.setText("sk-ant-x")
    with qtbot.waitSignal(page.key_save_requested) as blocker:
        qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["sk-ant-x"]


def test_key_box_hides_what_is_typed(page):
    assert page.key_box.echoMode() == page.key_box.EchoMode.Password


def test_test_button_waits_then_shows_a_failure_and_reenables(qtbot, page):
    page.set_key_saved(True)
    with qtbot.waitSignal(page.key_test_requested):
        qtbot.mouseClick(page.test_button, Qt.MouseButton.LeftButton)
    assert not page.test_button.isEnabled()
    page.show_key_result(False, "Could not reach the Claude API.")
    assert "Could not reach the Claude API." in page.key_status.text()
    assert page.key_status.isVisible()
    assert page.test_button.isEnabled()


def test_test_button_needs_a_saved_key(page):
    page.set_key_saved(False)
    assert not page.test_button.isEnabled()


def test_remove_asks_for_removal(qtbot, page):
    page.set_key_saved(True)
    with qtbot.waitSignal(page.key_remove_requested):
        qtbot.mouseClick(page.remove_button, Qt.MouseButton.LeftButton)


def test_totals_line_shows_today_month_cap_and_count(page):
    page.load(Config(ai_monthly_cap_cents=250))
    page.show_totals(Totals(today=0.0123, month=0.5, requests_month=7))
    assert page.usage_label.text() == "Today $0.0123 · This month $0.5000 of $2.50 · 7 requests"


def test_privacy_line_says_what_is_sent(page):
    assert "sends that text to Anthropic's Claude API" in page.privacy_label.text()


def test_privacy_link_is_its_own_link_label_so_it_takes_the_accent(page):
    # A link inside a style-sheet-styled label (cardDescription) draws in default blue on dark.
    assert "<a " not in page.privacy_label.text()
    assert page.privacy_link.openExternalLinks() and "privacy.anthropic.com" in page.privacy_link.text()
    assert page.privacy_link.objectName() == ""


def test_switch_describes_only_what_ships():
    from proofline.ai_settings_page import SWITCH_DESCRIPTION

    assert SWITCH_DESCRIPTION == "Rewords a sentence with Claude, only when you ask"
