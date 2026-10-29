import pytest
from PyQt6.QtCore import Qt

from proofline.ai_model_list import ModelChoice
from proofline.ai_page_text import (
    ADDRESS_DESCRIPTION,
    OTHER_KEY_DESCRIPTION,
    UNTESTED_NOTE,
    insecure_text,
    warning_text,
)
from proofline.ai_prices import ModelPrice, most_expensive
from proofline.ai_providers import PROVIDER_IDS, PROVIDERS, provider
from proofline.ai_settings_page import AiPage
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


def choose(page, pid):
    index = page.provider_box.findData(pid)
    page.provider_box.setCurrentIndex(index)
    page.provider_box.activated.emit(index)


def pick_other_model(page):
    page.model_box.setCurrentIndex(page.model_box.count() - 1)


def item_texts(combo):
    return [combo.itemText(i) for i in range(combo.count())]


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
    labels = item_texts(page.model_box)
    assert labels[0] == "Haiku 5.5 ($0.10 / $0.50 per million tokens)"
    assert labels[-1] == "Other model..."
    assert len(labels) == 4


def test_provider_drop_down_lists_every_provider_and_marks_untested_ones(page):
    assert [page.provider_box.itemData(i) for i in range(page.provider_box.count())] == list(PROVIDER_IDS)
    texts = item_texts(page.provider_box)
    assert texts[0] == "Claude" and "(untested)" not in texts[0]
    assert "OpenAI (untested)" in texts


def test_choosing_a_provider_saves_it_and_announces_it(qtbot, page):
    with qtbot.waitSignal(page.provider_chosen) as blocker:
        choose(page, "gemini")
    assert blocker.args == ["gemini"]
    assert page.current_provider() == "gemini"
    assert page.changes == [{"ai_provider": "gemini"}]


def test_choosing_a_provider_clears_the_key_box(page):
    page.key_box.setText("sk-typed")
    choose(page, "groq")
    assert page.key_box.text() == ""


def test_load_of_another_provider_keeps_the_key_box(page):
    page.key_box.setText("sk-typed")
    page.load(Config(ai_provider="groq"))
    assert page.current_provider() == "groq"
    assert page.key_box.text() == "sk-typed"


def test_key_box_never_shows_a_saved_key(page):
    page.key_box.setText("sk-ant-typed")
    page.set_key_saved("anthropic", True)
    assert page.key_box.isHidden() and page.key_box.text() == ""
    assert page.key_saved_label.isVisible() and page.remove_button.isVisible()
    assert not page.save_button.isVisible()
    page.set_key_saved("anthropic", False)
    assert page.key_box.isVisible() and not page.remove_button.isVisible()


def test_key_state_for_another_provider_is_ignored(page):
    page.set_key_saved("anthropic", False)
    page.set_key_saved("openai", True)
    assert page.key_box.isVisible() and not page.key_saved_label.isVisible()


def test_save_emits_the_shown_provider_and_the_typed_key(qtbot, page):
    choose(page, "openai")
    page.set_key_saved("openai", False)
    page.key_box.setText("sk-x")
    with qtbot.waitSignal(page.key_save_requested) as blocker:
        qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["openai", "sk-x"]


def test_key_box_hides_what_is_typed(page):
    assert page.key_box.echoMode() == page.key_box.EchoMode.Password


def test_test_button_waits_then_shows_a_failure_and_reenables(qtbot, page):
    page.set_key_saved("anthropic", True)
    with qtbot.waitSignal(page.key_test_requested) as blocker:
        qtbot.mouseClick(page.test_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["anthropic"]
    assert not page.test_button.isEnabled()
    page.show_key_result("anthropic", False, "Could not reach the Claude API.")
    assert "Could not reach the Claude API." in page.key_status.text()
    assert page.key_status.isVisible()
    assert page.test_button.isEnabled()


def test_result_for_another_provider_is_not_shown(page):
    page.set_key_saved("anthropic", True)
    page.show_key_result("openai", True, "The key works.")
    assert page.key_status.text() == ""


def test_test_button_needs_a_saved_key(page):
    page.set_key_saved("anthropic", False)
    assert not page.test_button.isEnabled()


def test_remove_asks_for_removal_of_the_shown_provider(qtbot, page):
    page.set_key_saved("anthropic", True)
    with qtbot.waitSignal(page.key_remove_requested) as blocker:
        qtbot.mouseClick(page.remove_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["anthropic"]


def test_usage_line_shows_the_text_it_is_given(page):
    page.show_usage("Today $0.0123 \u00b7 This month $0.5000 of $2.50 \u00b7 7 requests")
    assert page.usage_label.text() == "Today $0.0123 \u00b7 This month $0.5000 of $2.50 \u00b7 7 requests"


def test_address_save_announces_whether_it_changed(qtbot, page):
    choose(page, "ollama")
    page.address_box.setText("http://localhost:11500/")
    with qtbot.waitSignal(page.address_saved) as blocker:
        page.address_save_button.click()
    assert blocker.args == ["ollama", "http://localhost:11434", "http://localhost:11500"]
    assert page.changes[-1] == {"ai_ollama_url": "http://localhost:11500"}
    page.load(Config(ai_provider="ollama", ai_ollama_url="http://localhost:11500"))  # the saved config comes back
    with qtbot.waitSignal(page.address_saved) as blocker:
        page.address_save_button.click()
    assert blocker.args == ["ollama", "http://localhost:11500", "http://localhost:11500"]
    assert len(page.changes) == 2


def test_invalid_address_is_not_saved_and_the_error_shows_in_the_key_status(qtbot, page):
    choose(page, "other")
    page.address_box.setText("ftp://nope.example")
    seen = []
    page.address_saved.connect(lambda *args: seen.append(args))
    page.address_save_button.click()
    assert seen == []
    assert page.key_status.text() != "" and page.key_status.isVisible()


def test_address_test_asks_for_a_test_of_the_shown_provider(qtbot, page):
    choose(page, "ollama")
    with qtbot.waitSignal(page.key_test_requested) as blocker:
        qtbot.mouseClick(page.address_test_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["ollama"]
    assert not page.address_test_button.isEnabled()
    page.show_key_result("ollama", True, "The key works.")
    assert page.address_test_button.isEnabled()


def test_address_test_stays_disabled_mid_test_until_its_result_arrives(page):
    choose(page, "ollama")
    page.address_test_button.click()
    assert not page.address_test_button.isEnabled()
    choose(page, "other")
    choose(page, "ollama")
    assert not page.address_test_button.isEnabled()  # the test is still running
    page.show_key_result("ollama", True, "The server works.")
    assert page.address_test_button.isEnabled()


def test_refresh_button_asks_for_the_shown_providers_models(qtbot, page):
    choose(page, "openrouter")
    with qtbot.waitSignal(page.models_refresh_requested) as blocker:
        page.refresh_button.click()
    assert blocker.args == ["openrouter"]


def test_set_model_choices_fills_the_list_and_keeps_other_model_last(page):
    choose(page, "openrouter")
    choices = (ModelChoice("m-a", "Model A", ModelPrice("openrouter", "m-a", "Model A", 0.5, 1.5)),)
    page.set_model_choices("openrouter", choices)
    texts = item_texts(page.model_box)
    assert texts[0] == "Model A ($0.50 / $1.50 per million tokens)"
    assert texts[-1] == "Other model..."


def test_picking_other_model_shows_the_typed_name_box_and_typing_saves_it(page):
    choose(page, "openai")
    pick_other_model(page)
    assert page.model_name_box.isVisible()
    page.model_name_box.setText("gpt-7-new")
    page.model_name_box.editingFinished.emit()
    assert page.changes[-1] == {"ai_models": ("openai=gpt-7-new",)}


def test_invalid_typed_model_is_not_saved(page):
    choose(page, "openai")
    pick_other_model(page)
    count = len(page.changes)
    page.model_name_box.setText("a b")
    page.model_name_box.editingFinished.emit()
    assert len(page.changes) == count
    assert page.model_status.text() != ""


def test_typed_model_name_survives_a_settings_reload_until_the_provider_changes(page):
    choose(page, "openai")
    pick_other_model(page)
    page.model_name_box.setText("gpt-7-draft")
    page.load(Config(ai_provider="openai", ai_enabled=True))
    assert page.model_name_box.isVisible() and page.model_name_box.text() == "gpt-7-draft"
    assert page.model_box.currentText() == "Other model..."
    choose(page, "groq")
    assert page.model_name_box.text() == ""


def test_typed_model_note_names_the_dearest_live_openrouter_model(page):
    choose(page, "openrouter")
    cheap = ModelPrice("openrouter", "m-a", "Model A", 0.5, 1.5)
    dear = ModelPrice("openrouter", "m-b", "Model B", 3.0, 15.0)
    page.set_model_choices("openrouter", (ModelChoice("m-a", "Model A", cheap), ModelChoice("m-b", "Model B", dear)))
    pick_other_model(page)
    assert page.estimated_label.isVisible()
    assert page.estimated_label.text() == "Cost estimated at Model B's price"


def test_typed_model_note_for_a_priced_provider_and_none_for_ollama(page):
    choose(page, "gemini")
    pick_other_model(page)
    assert page.estimated_label.text() == f"Cost estimated at {most_expensive('gemini').label}'s price"
    choose(page, "ollama")
    assert page.estimated_label.isHidden()


def test_cloud_shows_key_card_and_limit(page):
    choose(page, "gemini")
    assert page.key_card.isVisible() and page.address_card.isHidden()
    assert page.cap_card.isVisible() and page.refresh_button.isHidden()
    assert page.warning_label.text() == warning_text(provider("gemini"))
    assert page.model_group.text() == "Model and spending"
    assert page.provider_group.text() == "Provider"


def test_ollama_shows_address_and_hides_key_and_limit(page):
    choose(page, "ollama")
    assert page.address_card.isVisible() and page.key_card.isHidden()
    assert page.cap_card.isHidden() and page.address_test_button.isVisible()
    assert page.refresh_button.isVisible() and page.privacy_link.isHidden()
    assert page.address_card.description_label.text() == ADDRESS_DESCRIPTION["ollama"]
    assert page.model_group.text() == "Model and usage"


def test_other_shows_optional_key_and_address(page):
    choose(page, "other")
    assert page.key_card.isVisible() and page.key_card.description_label.text() == OTHER_KEY_DESCRIPTION
    assert page.address_card.isVisible() and page.cap_card.isHidden()
    assert page.model_group.text() == "Model and usage"


def test_untested_label_for_untested_providers(page):
    choose(page, "openai")
    assert page.untested_label.isVisible() and page.untested_label.text() == UNTESTED_NOTE
    choose(page, "anthropic")
    assert page.untested_label.isHidden()


def test_insecure_label_for_lan_http(page):
    choose(page, "other")
    page.load(Config(ai_provider="other", ai_other_url="http://lan.example:1234/v1"))
    assert page.insecure_label.isVisible()
    assert page.insecure_label.text() == insecure_text("http://lan.example:1234/v1")
    page.load(Config(ai_provider="other", ai_other_url="http://127.0.0.1:1234/v1"))
    assert page.insecure_label.isHidden()
    page.load(Config(ai_provider="other", ai_other_url="https://lan.example/v1"))
    assert page.insecure_label.isHidden()


def test_privacy_line_says_what_is_sent(page):
    assert "sends that text (Test sends a short fixed sentence) to Claude with your key" in page.privacy_label.text()


def test_key_box_placeholder_is_neutral_for_every_provider(page):
    choose(page, "gemini")
    assert page.key_box.placeholderText() == "Paste your API key"
    assert "sk-ant" not in page.key_box.placeholderText()
    choose(page, "anthropic")
    assert "sk-ant" not in page.key_box.placeholderText()


def test_privacy_lines_follow_the_shown_provider(page):
    choose(page, "gemini")
    assert page.warning_label.isVisible()
    assert page.warning_label.text() == warning_text(provider("gemini"))
    choose(page, "ollama")
    assert "Your text stays on this computer." in page.privacy_label.text()
    assert page.warning_label.isHidden()
    assert not page.privacy_link.isVisible() and page.key_card.isHidden()
    page.load(Config(ai_provider="ollama", ai_ollama_url="http://ollama.example:11434"))
    assert "Your text goes to the computer at this address." in page.privacy_label.text()
    assert "This address is not encrypted" in page.insecure_label.text()


def test_privacy_link_shows_the_shown_providers_data_page(page):
    choose(page, "gemini")
    assert page.privacy_link.isVisible()
    assert provider("gemini").privacy_url in page.privacy_link.text()


def test_privacy_link_is_its_own_link_label_so_it_takes_the_accent(page):
    # A link inside a style-sheet-styled label (cardDescription) draws in default blue on dark.
    assert "<a " not in page.privacy_label.text()
    assert page.privacy_link.openExternalLinks() and "privacy.anthropic.com" in page.privacy_link.text()
    assert page.privacy_link.objectName() == ""


def test_switch_describes_only_what_ships():
    from proofline.ai_settings_page import SWITCH_DESCRIPTION

    assert SWITCH_DESCRIPTION == "Rewords a sentence or finds more issues with the AI provider you choose, only when you ask"
    assert "Claude" not in SWITCH_DESCRIPTION


def test_search_finds_every_provider_by_its_label(page):
    for spec in PROVIDERS:
        assert page.provider_card.matches(spec.label)


def test_search_does_not_bring_back_a_card_the_provider_does_not_use(page):
    choose(page, "ollama")
    page.filter("")
    assert page.key_card.isHidden() and not page.cap_card.isVisible()
    assert page.address_card.isVisible()


def test_address_test_waits_until_the_address_is_saved(qtbot, page):
    choose(page, "ollama")
    assert page.address_test_button.isEnabled()
    page.address_box.setText("http://localhost:11500")
    assert not page.address_test_button.isEnabled()
    assert page.address_test_button.toolTip() == "Save the address first"
    page.address_save_button.click()
    page.load(Config(ai_provider="ollama", ai_ollama_url="http://localhost:11500"))  # the saved config comes back
    assert page.address_test_button.isEnabled()
    assert page.address_test_button.toolTip() == ""


def test_status_and_note_labels_show_server_text_as_plain_text(page):
    page.show_key_result("anthropic", False, "The server said <b>no</b>")
    assert page.key_status.textFormat() == Qt.TextFormat.PlainText
    assert page.key_status.text() == "The server said <b>no</b>"
    assert page.privacy_label.textFormat() == Qt.TextFormat.PlainText


def test_switching_provider_during_a_test_re_enables_the_new_providers_buttons_when_the_result_comes(page):
    choose(page, "openai")
    page.set_key_saved("openai", True)
    page.test_button.click()  # running for openai
    choose(page, "gemini")
    page.set_key_saved("gemini", True)
    assert not page.test_button.isEnabled()  # gemini's Test waits: openai's test is still running
    page.show_key_result("openai", True, "The key works.")  # the old provider's result arrives
    assert page.test_button.isEnabled()
    assert page.address_test_button.isEnabled()
