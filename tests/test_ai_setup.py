import threading
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest

from proofline import workers
from proofline.ai_client import AiError, AiResult
from proofline.ai_model_list import ModelChoice
from proofline.ai_page_text import KEY_REFUSED_INSECURE, RESAVE_KEY_TEXT, usage_text
from proofline.ai_prices import ModelPrice
from proofline.ai_providers import provider
from proofline.ai_service import BUSY_MESSAGE, AiService
from proofline.ai_settings_page import AiPage
from proofline.ai_setup import (
    KEY_READ_FAILED_MESSAGE,
    KEY_REMOVE_FAILED_MESSAGE,
    KEY_WORKS_MESSAGE,
    PASTE_FIRST_MESSAGE,
    TEST_ERROR_MESSAGE,
    AiSetup,
    key_test_request,
)
from proofline.ai_usage import read_entries
from proofline.config import Config, load_config, save_config


class Keys:
    """Stands in for KeyStore: one key per provider, in memory."""

    def __init__(self, key=None):
        self.keys = {"anthropic": key} if key else {}
        self.read_error = None  # raised by load(), like a key store that cannot be read

    def save(self, pid, key):
        if not key.strip():
            raise ValueError("empty")
        self.keys[pid] = key.strip()

    def load(self, pid):
        if self.read_error:
            raise self.read_error
        return self.keys.get(pid)

    def delete(self, pid):
        self.keys.pop(pid, None)


class Backend:
    def __init__(self, error=None, gate=None):
        self.error, self.gate, self.sent = error, gate, []

    def send(self, request, model):
        if self.gate is not None:
            self.gate.wait(5)
        self.sent.append(request)
        if self.error:
            raise self.error
        return AiResult({"ok": True}, 30, 5)


def no_models(spec, base_url, key):
    return ()


def choose(page, pid):
    """The user picks pid in the provider drop-down."""
    index = page.provider_box.findData(pid)
    page.provider_box.setCurrentIndex(index)
    page.provider_box.activated.emit(index)


@pytest.fixture
def make(qtbot, tmp_path):
    def build(key=None, error=None, config=None, keys=None, gate=None, list_models=no_models):
        state = {"config": config or Config(ai_enabled=True)}
        keys = keys if keys is not None else Keys(key)
        backend = Backend(error, gate)
        rig = SimpleNamespace(state=state, keys=keys, backend=backend, used=[], list_calls=[])
        page = AiPage()
        qtbot.addWidget(page)

        def apply(changes):  # what SettingsWindow does: save the config, then reload the page
            state["config"] = replace(state["config"], **changes)
            page.load(state["config"])

        def apply_and_react(changes):  # the app's _set_config: the page's save, then the AI-on hook
            previous = state["config"]
            apply(changes)
            if "setup" in holder:
                holder["setup"].config_changed(previous)

        holder = {}
        page.changed.connect(apply_and_react)

        def factory(spec, key, address):
            rig.used.append((spec.id, key, address))
            return backend

        def lists(spec, base_url, key, transport=None):
            rig.list_calls.append((spec.id, base_url, key))
            return list_models(spec, base_url, key)

        service = AiService(lambda: state["config"], factory, lambda pid: keys.load(pid),
                            tmp_path / "ai_usage.jsonl", lambda: datetime(2026, 10, 26, 12))
        setup = AiSetup(page, service, lambda: state["config"], keys, lists)  # built before the first load, as in app.py
        page.load(state["config"])
        page.show()
        rig.page, rig.service, rig.setup = page, service, setup
        holder["setup"] = setup
        rig.ledger = tmp_path / "ai_usage.jsonl"
        return rig
    return build


def test_page_starts_with_the_saved_state(make):
    rig = make(key="sk-ant-saved")
    assert rig.page.key_saved_label.isVisible()
    rig = make()
    assert rig.page.key_box.isVisible()


def test_save_stores_the_key_and_hides_it(make):
    rig = make()
    rig.page.key_box.setText("sk-ant-new")
    rig.page.save_button.click()
    assert rig.keys.keys == {"anthropic": "sk-ant-new"}
    assert rig.page.key_box.isHidden() and rig.page.key_box.text() == ""


def test_saving_an_empty_key_says_so(make):
    rig = make()
    rig.page.key_box.setText("   ")
    rig.page.save_button.click()
    assert rig.keys.keys == {}
    assert rig.page.key_status.text() == PASTE_FIRST_MESSAGE == "Paste a key first."


def test_save_says_so_when_the_key_cannot_be_read_back(make):
    # 0.3.0 packages lacked win32timezone: the key was stored but every read failed, silently.
    rig = make()
    rig.keys.read_error = ModuleNotFoundError("No module named 'win32timezone'")
    rig.page.key_box.setText("sk-ant-new")
    rig.page.save_button.click()
    assert rig.keys.keys == {"anthropic": "sk-ant-new"}
    assert rig.page.key_status.isVisible()
    assert rig.page.key_status.text() == KEY_READ_FAILED_MESSAGE
    assert rig.page.key_status.objectName() == "statusError"
    assert not rig.page.test_button.isEnabled()


def test_showing_the_page_says_so_when_the_key_cannot_be_read(make):
    rig = make(key="sk-ant-saved")
    rig.keys.read_error = OSError("Credential Manager unavailable")
    rig.page.hide()
    rig.page.show()
    assert rig.page.key_box.isVisible()
    assert rig.page.key_status.text() == KEY_READ_FAILED_MESSAGE


def test_remove_deletes_the_key(make):
    rig = make(key="sk-ant-saved")
    rig.page.remove_button.click()
    assert rig.keys.keys == {}
    assert rig.page.key_box.isVisible()


def test_test_button_sends_one_small_request_and_reports_success(qtbot, make):
    rig = make(key="sk-ant-saved")
    with qtbot.waitSignal(rig.service.finished):
        rig.page.test_button.click()
    assert rig.backend.sent == [key_test_request()]
    assert key_test_request().max_tokens == 1000 and key_test_request().job == "test"
    assert rig.page.key_status.text() == KEY_WORKS_MESSAGE == "The key works."
    assert rig.page.test_button.isEnabled()
    assert len(read_entries(rig.ledger)) == 1
    assert "1 request" in rig.page.usage_label.text()


def test_test_failure_shows_the_message(qtbot, make):
    rig = make(key="sk-ant-bad", error=AiError("auth", "The Claude API did not accept the API key."))
    with qtbot.waitSignal(rig.service.failed):
        rig.page.test_button.click()
    assert rig.page.key_status.text() == "The Claude API did not accept the API key."
    assert rig.page.test_button.isEnabled()


def test_test_while_ai_is_off_explains_why(make):
    rig = make(key="sk-ant-saved", config=Config())
    rig.page.test_button.click()
    assert rig.page.key_status.text() == "AI is turned off in Settings."
    assert rig.page.test_button.isEnabled()


def test_showing_the_page_refreshes_the_usage_line(make):
    rig = make()
    rig.page.hide()
    rig.page.usage_label.setText("")
    rig.page.show()
    assert rig.page.usage_label.text().startswith("Today $0.0000")


def test_changing_the_spending_limit_updates_the_usage_line_without_reloading_the_page(make):
    rig = make()
    assert "of $1.00" in rig.page.usage_label.text()  # the default limit, 100 cents
    previous = rig.state["config"]
    rig.state["config"] = replace(previous, ai_monthly_cap_cents=300)  # saved, but the page is not reloaded
    rig.setup.config_changed(previous)
    assert "of $3.00" in rig.page.usage_label.text()


def test_other_key_saved_for_no_address_is_still_flagged_after_a_restart(make):
    config = Config(ai_enabled=True, ai_provider="other", ai_other_url=A_ADDRESS, ai_models=("other=local-model",))
    rig = make(config=config, keys=Keys())
    rig.keys.keys["other"] = "k1"  # saved while an earlier address was in use: not bound to A_ADDRESS
    rig.setup.refresh()  # what a fresh start shows: the page loads the saved state
    assert rig.page.key_status.text() == RESAVE_KEY_TEXT


def test_other_key_whose_address_could_not_be_recorded_is_flagged(make):
    config = Config(ai_enabled=True, ai_provider="other", ai_other_url=A_ADDRESS, ai_models=("other=local-model",))
    rig = make(config=config, keys=Keys())
    rig.page.changed.disconnect()  # the settings save fails: no change is recorded in the config
    rig.page.key_box.setText("k1")
    rig.page.save_button.click()
    assert rig.keys.keys == {"other": "k1"}
    assert rig.state["config"].ai_other_key_address == ""
    assert rig.page.key_status.text() == RESAVE_KEY_TEXT


def test_other_key_binding_is_written_to_config_and_read_back_after_a_restart(tmp_path):
    path = tmp_path / "config.json"
    saved = Config(ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS)
    save_config(saved, path)
    restored = load_config(path)
    assert restored.ai_other_key_address == A_ADDRESS
    assert restored.other_key_applies()


def test_test_button_is_enabled_again_when_the_key_store_cannot_be_read(make):
    rig = make(key="sk-ant-saved")
    assert rig.page.test_button.isEnabled()
    rig.keys.read_error = RuntimeError("Credential Manager is busy")  # an error the page does not expect
    rig.page.test_button.click()
    assert rig.page.test_button.isEnabled()
    assert rig.page.key_status.text() == TEST_ERROR_MESSAGE
    assert rig.page._test_pid is None


def test_save_and_remove_refresh_ai_availability(make):
    rig = make()
    assert not rig.service.available()
    rig.page.key_box.setText("sk-ant-new")
    rig.page.save_button.click()
    assert rig.service.available()
    rig.page.remove_button.click()
    assert not rig.service.available()


def test_switching_provider_clears_the_key_box_and_save_uses_the_shown_provider(make):
    rig = make()
    choose(rig.page, "openai")
    rig.page.key_box.setText("sk-A")
    choose(rig.page, "gemini")
    assert rig.page.key_box.text() == ""
    rig.page.key_box.setText("g-key")
    rig.page.save_button.click()
    assert rig.keys.keys == {"gemini": "g-key"}


def test_settings_reload_keeps_unsaved_key_text(make):
    rig = make()
    rig.page.key_box.setText("sk-A")
    rig.page.load(replace(rig.state["config"], ai_monthly_cap_cents=500))
    assert rig.page.key_box.text() == "sk-A"


def test_remove_and_test_use_the_shown_provider(qtbot, make):
    rig = make(keys=Keys())
    rig.keys.keys["groq"] = "gsk-one"
    choose(rig.page, "groq")
    rig.page.remove_button.click()
    assert "groq" not in rig.keys.keys
    rig.page.key_box.setText("gsk-two")
    rig.page.save_button.click()
    with qtbot.waitSignal(rig.service.finished):
        rig.page.test_button.click()
    assert rig.used[-1] == ("groq", "gsk-two", "")
    assert rig.backend.sent == [key_test_request()]


def test_switch_away_and_back_keeps_model_address_and_key(make):
    rig = make()
    page = rig.page
    choose(page, "ollama")
    page.address_box.setText("http://localhost:11500")
    page.address_save_button.click()
    choose(page, "gemini")
    page.key_box.setText("g-key")
    page.save_button.click()
    page.model_box.setCurrentIndex(page.model_box.findData("gemini-2.5-pro"))
    choose(page, "anthropic")
    choose(page, "gemini")
    assert page.model_box.currentData() == "gemini-2.5-pro"
    assert page.key_saved_label.isVisible() and rig.keys.keys["gemini"] == "g-key"
    choose(page, "ollama")
    assert page.address_box.text() == "http://localhost:11500"


def test_key_for_insecure_remote_address_is_refused(make):
    rig = make()
    choose(rig.page, "other")
    rig.page.address_box.setText("http://lan.example:1234/v1")
    rig.page.address_save_button.click()
    rig.page.key_box.setText("local-key")
    rig.page.save_button.click()
    assert rig.keys.keys == {}
    assert rig.page.key_status.text() == KEY_REFUSED_INSECURE


def test_changing_other_address_deletes_its_key_but_resaving_the_same_does_not(make):
    rig = make(keys=Keys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url="http://localhost:1234/v1")
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    rig.page.address_box.setText("http://localhost:9999/v1")
    rig.page.address_save_button.click()
    assert "other" not in rig.keys.keys
    rig.page.key_box.setText("k2")
    rig.page.save_button.click()
    rig.page.address_box.setText("http://localhost:9999/v1")
    rig.page.address_save_button.click()
    assert rig.keys.keys == {"other": "k2"}


def test_test_result_for_previous_provider_is_ignored(qtbot, make):
    gate = threading.Event()
    rig = make(keys=Keys(), gate=gate)
    rig.keys.keys.update(openai="sk-o", gemini="g-k")
    choose(rig.page, "openai")
    rig.page.test_button.click()
    choose(rig.page, "gemini")
    assert rig.page.key_status.text() == ""
    with qtbot.waitSignal(rig.service.finished):
        gate.set()
    assert rig.page.key_status.text() == ""
    assert rig.page.current_provider() == "gemini"


def test_refresh_fills_models_and_openrouter_prices(qtbot, make):
    choices = (
        ModelChoice("m-a", "Model A", ModelPrice("openrouter", "m-a", "Model A", 0.5, 1.5)),
        ModelChoice("m-b", "Model B", ModelPrice("openrouter", "m-b", "Model B", 1.0, 2.0)),
    )
    rig = make(list_models=lambda spec, base_url, key: choices)
    choose(rig.page, "openrouter")
    qtbot.waitUntil(lambda: rig.page.model_box.count() == 3)
    texts = [rig.page.model_box.itemText(i) for i in range(rig.page.model_box.count())]
    assert texts[0].startswith("Model A") and texts[1].startswith("Model B")
    assert texts[-1] == "Other model..."
    assert rig.service.price(provider("openrouter"), "m-a") is not None


def test_refresh_with_an_empty_address_fetches_nothing(make):
    rig = make()
    choose(rig.page, "other")
    rig.page.refresh_button.click()
    assert rig.list_calls == []


def test_openrouter_list_is_fetched_without_any_key(qtbot, make):
    """OpenRouter's model list is public: no key is sent with it, even when one is saved."""
    rig = make(keys=Keys())
    rig.keys.keys.update(anthropic="sk-ant-saved", openrouter="or-key")
    choose(rig.page, "openrouter")
    qtbot.waitUntil(lambda: bool(rig.list_calls))
    assert rig.list_calls == [("openrouter", "https://openrouter.ai/api/v1", None)]


class StuckKeys(Keys):
    """A key store that can read and save but cannot delete (Credential Manager refusing the delete)."""

    def delete(self, pid):
        raise OSError("delete refused")


def test_first_address_save_keeps_the_other_key(make):
    """The key was never sent anywhere before an address was saved, so giving it an address keeps it."""
    rig = make(keys=Keys())
    rig.keys.keys["other"] = "k1"
    choose(rig.page, "other")
    rig.page.address_box.setText("http://localhost:1234/v1")
    rig.page.address_save_button.click()
    assert rig.keys.keys == {"other": "k1"}
    assert "removed because the address changed" not in rig.page.key_status.text()


def test_changing_other_address_says_the_key_was_removed(make):
    rig = make(keys=Keys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url="http://localhost:1234/v1")
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    rig.page.address_box.setText("http://localhost:9999/v1")
    rig.page.address_save_button.click()
    assert "other" not in rig.keys.keys
    assert rig.page.key_status.text() == (
        "The key for Other server was removed because the address changed. Save it again for the new address.")
    assert rig.page.key_status.objectName() == "statusError"


def test_failed_delete_leaves_the_key_bound_to_no_address_until_it_is_saved_again(qtbot, make):
    rig = make(keys=StuckKeys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url="http://localhost:1234/v1",
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    rig.page.address_box.setText("http://localhost:9999/v1")
    rig.page.address_save_button.click()
    assert rig.keys.keys == {"other": "k1"}
    assert rig.page.key_status.text() == KEY_REMOVE_FAILED_MESSAGE
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, "http://localhost:9999/v1")
    rig.page.key_box.setText("k2")
    rig.page.save_button.click()
    assert rig.keys.keys == {"other": "k2"}
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", "k2", "http://localhost:9999/v1")


def test_refresh_never_sends_another_providers_key(qtbot, make):
    rig = make(keys=Keys())
    rig.keys.keys.update(anthropic="sk-ant-saved", ollama="ol-key")
    choose(rig.page, "ollama")
    rig.page.refresh_button.click()
    qtbot.waitUntil(lambda: bool(rig.list_calls))
    assert [key for _, _, key in rig.list_calls] == [None]


def test_openrouter_selected_at_startup_fetches_its_prices_once(qtbot, make):
    """Without this, OpenRouter refuses every request after a restart until the user presses Refresh."""
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    keys = Keys()
    keys.keys["openrouter"] = "or-key"
    rig = make(config=config, keys=keys)
    qtbot.waitUntil(lambda: not workers._active_tasks and bool(rig.list_calls))
    assert rig.list_calls == [("openrouter", "https://openrouter.ai/api/v1", None)]


def test_openrouter_not_selected_at_startup_fetches_nothing(qtbot, make):
    rig = make(config=Config(ai_enabled=True, ai_provider="anthropic"))
    qtbot.wait(20)
    assert rig.list_calls == []


def test_openrouter_refusal_for_no_prices_fetches_the_list_again(qtbot, make):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    keys = Keys()
    keys.keys["openrouter"] = "or-key"
    rig = make(config=config, keys=keys)
    kinds = []
    rig.service.failed.connect(lambda req, message, kind: kinds.append(kind))
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 1)
    assert rig.service.submit(key_test_request()) is False
    assert kinds == ["no_prices"]
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 2)


def test_models_fetched_for_an_address_changed_meanwhile_are_dropped(qtbot, make):
    gate = threading.Event()

    def slow(spec, base_url, key):
        gate.wait(5)
        return (ModelChoice("old-model", "Old model", None),)

    rig = make(list_models=slow)
    choose(rig.page, "ollama")
    rig.page.refresh_button.click()  # fetch starts for the saved address, http://localhost:11434
    rig.state["config"] = replace(rig.state["config"], ai_ollama_url="http://ollama.example:11434")
    rig.page.load(rig.state["config"])
    gate.set()
    qtbot.waitUntil(lambda: not workers._active_tasks)  # the result has been delivered to the GUI thread
    assert rig.page.model_box.findData("old-model") == -1


def test_a_refused_test_reports_busy_and_the_running_test_still_shows_its_result(qtbot, make):
    gate = threading.Event()
    rig = make(keys=Keys(), gate=gate)
    rig.keys.keys["openai"] = "sk-o"
    choose(rig.page, "openai")
    rig.page.test_button.click()  # running, held by the gate
    rig.page.key_test_requested.emit("openai")  # a second Test while the first runs
    assert rig.page.key_status.text() == BUSY_MESSAGE
    with qtbot.waitSignal(rig.service.finished):
        gate.set()
    assert rig.page.key_status.text() == KEY_WORKS_MESSAGE


def test_loading_another_provider_shows_its_saved_key_state(make):
    rig = make(keys=Keys())
    rig.keys.keys["gemini"] = "AIza-saved"  # Claude is shown, with no key
    assert rig.page.key_box.isVisible()
    rig.page.load(Config(ai_enabled=True, ai_provider="gemini"))  # a settings save reloads the page
    assert rig.page.current_provider() == "gemini"
    assert not rig.page.key_saved_label.isHidden() and rig.page.key_box.isHidden()


def test_loading_ollama_shows_its_token_usage_line(make, tmp_path):
    rig = make()
    config = Config(ai_enabled=True, ai_provider="ollama", ai_model="llama3.2",
                    ai_ollama_url="http://localhost:11434")
    rig.page.load(config)
    expected = usage_text(provider("ollama"), "http://localhost:11434", "llama3.2",
                          None, rig.service.token_totals("ollama"), config.ai_monthly_cap_cents)
    assert rig.page.usage_label.text() == expected
    assert "tokens" in rig.page.usage_label.text() and "$" not in rig.page.usage_label.text()


A_ADDRESS = "http://localhost:1234/v1"
B_ADDRESS = "http://localhost:9999/v1"


def restarted_service(rig):
    """A new AiService, as after a restart: it knows only the saved config and the key store."""
    def factory(spec, key, address):
        rig.used.append((spec.id, key, address))
        return rig.backend
    return AiService(lambda: rig.state["config"], factory, lambda pid: rig.keys.load(pid), rig.ledger,
                     lambda: datetime(2026, 10, 26, 12))


def set_other_address(rig, address):
    rig.page.address_box.setText(address)
    rig.page.address_save_button.click()


def test_saving_an_other_key_binds_it_to_the_address_shown(make):
    rig = make(keys=Keys())
    choose(rig.page, "other")
    set_other_address(rig, A_ADDRESS)
    rig.page.key_box.setText("k1")
    rig.page.save_button.click()
    assert rig.keys.keys == {"other": "k1"}
    assert rig.state["config"].ai_other_key_address == A_ADDRESS


def test_first_address_save_keeps_the_other_key_unbound_and_asks_for_a_new_save(qtbot, make):
    rig = make(keys=Keys())
    rig.state["config"] = replace(rig.state["config"], ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    rig.keys.keys["other"] = "k1"
    choose(rig.page, "other")
    set_other_address(rig, A_ADDRESS)
    assert rig.keys.keys == {"other": "k1"}  # kept, not deleted
    assert rig.state["config"].ai_other_key_address == ""  # but not bound to the first address
    assert rig.page.key_status.text() == RESAVE_KEY_TEXT
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, A_ADDRESS)


def test_key_saved_with_no_address_is_sent_only_after_it_is_saved_for_the_address(qtbot, make):
    rig = make(keys=Keys())
    rig.state["config"] = replace(rig.state["config"], ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    rig.page.key_box.setText("k1")
    rig.page.save_button.click()  # saved while no address exists
    set_other_address(rig, A_ADDRESS)
    assert rig.page.key_status.text() == RESAVE_KEY_TEXT
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, A_ADDRESS)
    rig.page.remove_button.click()
    rig.page.key_box.setText("k2")
    rig.page.save_button.click()
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", "k2", A_ADDRESS)


def test_key_from_a_failed_delete_is_not_bound_to_a_later_address_after_an_empty_one(qtbot, make):
    """A -> B (delete fails) -> no address -> C: the key saved for A must never reach C."""
    rig = make(keys=StuckKeys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS,
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    set_other_address(rig, B_ADDRESS)
    rig.state["config"] = replace(rig.state["config"], ai_other_url="")
    rig.page.load(rig.state["config"])
    set_other_address(rig, "http://localhost:5555/v1")
    assert rig.state["config"].ai_other_key_address == ""
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, "http://localhost:5555/v1")


def test_other_key_is_not_sent_to_a_new_address_after_a_restart_when_delete_failed(qtbot, make):
    rig = make(keys=StuckKeys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS,
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    set_other_address(rig, B_ADDRESS)
    assert rig.page.key_status.text() == KEY_REMOVE_FAILED_MESSAGE
    service = restarted_service(rig)
    with qtbot.waitSignal(service.finished):
        assert service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, B_ADDRESS)


def test_failed_delete_key_stays_unsent_when_the_old_address_comes_back(qtbot, make):
    rig = make(keys=StuckKeys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS,
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    set_other_address(rig, B_ADDRESS)
    set_other_address(rig, A_ADDRESS)
    with qtbot.waitSignal(rig.service.finished):
        assert rig.service.submit(key_test_request()) is True
    assert rig.used[-1] == ("other", None, A_ADDRESS)


def test_other_key_is_not_sent_to_a_new_address_by_the_model_list(qtbot, make):
    rig = make(keys=StuckKeys())
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS)
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    set_other_address(rig, B_ADDRESS)
    qtbot.waitUntil(lambda: not workers._active_tasks and bool(rig.list_calls))
    assert all(key is None for _, _, key in rig.list_calls)
    assert rig.list_calls[-1] == ("other", B_ADDRESS, None)


def test_test_buttons_stay_disabled_through_a_settings_reload_while_a_test_runs(qtbot, make):
    gate = threading.Event()
    rig = make(keys=Keys(), gate=gate)
    rig.keys.keys["other"] = "k1"
    rig.state["config"] = replace(rig.state["config"], ai_other_url=A_ADDRESS, ai_other_key_address=A_ADDRESS,
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    rig.page.address_test_button.click()  # running, held by the gate
    rig.page.load(rig.state["config"])  # a settings save reloads the page while the test runs
    assert not rig.page.address_test_button.isEnabled()
    assert not rig.page.test_button.isEnabled()
    with qtbot.waitSignal(rig.service.finished):
        gate.set()
    assert rig.page.address_test_button.isEnabled() and rig.page.test_button.isEnabled()
    assert rig.page.key_status.text() == KEY_WORKS_MESSAGE


class FakeTimer:
    """Stands in for QTimer.singleShot: records each scheduled call and runs it only when the test says so."""

    def __init__(self):
        self.scheduled = []

    def singleShot(self, msec, callback):
        self.scheduled.append((msec, callback))


@pytest.fixture
def timer(monkeypatch):
    fake = FakeTimer()
    monkeypatch.setattr("proofline.ai_setup.QTimer", fake)
    return fake


def failing_models(spec, base_url, key):
    raise RuntimeError("the model list could not be loaded")


def test_turning_ai_on_with_openrouter_selected_fetches_its_models_once(qtbot, make):
    rig = make(config=Config(ai_enabled=False, ai_provider="openrouter"))
    assert rig.list_calls == []
    rig.page.enabled_switch.click()
    qtbot.waitUntil(lambda: not workers._active_tasks and bool(rig.list_calls))
    assert rig.list_calls == [("openrouter", "https://openrouter.ai/api/v1", None)]


def test_turning_ai_on_with_another_provider_fetches_nothing(qtbot, make):
    rig = make(config=Config(ai_enabled=False, ai_provider="anthropic"))
    rig.page.enabled_switch.click()
    qtbot.wait(20)
    assert rig.list_calls == []


def test_a_failed_startup_fetch_retries_once_after_30_seconds(qtbot, make, timer):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    rig = make(config=config, list_models=failing_models)
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 1)
    assert [msec for msec, _ in timer.scheduled] == [30_000]
    _, retry = timer.scheduled[0]
    retry()  # the 30 seconds pass
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 2)
    assert len(timer.scheduled) == 1  # a failed retry schedules nothing more: no loop


def test_a_second_failing_fetch_while_a_retry_is_pending_schedules_no_more(qtbot, make, timer):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    rig = make(config=config, list_models=failing_models)
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 1)
    previous = replace(rig.state["config"], ai_enabled=False)
    rig.setup.config_changed(previous)  # AI turned on again while the retry waits
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 2)
    assert len(timer.scheduled) == 1


def test_a_pending_retry_does_nothing_if_ai_was_turned_off_meanwhile(qtbot, make, timer):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    rig = make(config=config, list_models=failing_models)
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 1)
    rig.state["config"] = replace(rig.state["config"], ai_enabled=False)
    timer.scheduled[0][1]()
    qtbot.wait(20)
    assert len(rig.list_calls) == 1


def test_a_successful_startup_fetch_schedules_no_retry(qtbot, make, timer):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=m-a",))
    rig = make(config=config)
    qtbot.waitUntil(lambda: not workers._active_tasks and len(rig.list_calls) == 1)
    assert timer.scheduled == []


def test_a_passing_ollama_test_names_the_server_not_a_key(qtbot, make):
    rig = make(keys=Keys(), config=Config(ai_enabled=True, ai_provider="ollama", ai_models=("ollama=llama3.2",)))
    choose(rig.page, "ollama")
    with qtbot.waitSignal(rig.service.finished):
        rig.page.address_test_button.click()
    assert rig.page.key_status.text() == "Ollama answered."


def test_a_passing_other_server_test_without_a_key_names_the_server(qtbot, make):
    rig = make(keys=Keys())
    rig.state["config"] = replace(rig.state["config"], ai_provider="other", ai_other_url=A_ADDRESS,
                                  ai_models=("other=local-model",))
    rig.page.load(rig.state["config"])
    choose(rig.page, "other")
    with qtbot.waitSignal(rig.service.finished):
        rig.page.address_test_button.click()
    assert rig.page.key_status.text() == "Other server answered."
