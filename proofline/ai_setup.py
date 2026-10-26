"""Connects the Settings AI page to the key stores, the AI request service and the model lists.

Kept out of app.py so it can be tested with a stand-in key store. Each action takes the provider it
was started for (the page passes it) and every result is shown for that provider only, so a key is
only ever tested or sent for the provider it was saved for. The Test button sends one small request
through AiService, so it follows the same rules (AI on, key saved, spending limit) and is recorded
in the usage ledger like any other request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from proofline.ai_client import AiError, AiRequest
from proofline.ai_keys import KeyStore
from proofline.ai_model_list import ModelChoice, fetch_models
from proofline.ai_page_text import KEY_REFUSED_INSECURE, RESAVE_KEY_TEXT, usage_text
from proofline.ai_providers import provider
from proofline.ai_service import BUSY_MESSAGE, OPENROUTER_ID, AiService
from proofline.ai_settings_page import LIVE_MODEL_PROVIDERS, AiPage
from proofline.config import OTHER_ID, Config, is_insecure_remote
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

TEST_JOB = "test"
OPENROUTER_RETRY_MS = 30_000  # a failed startup or AI-on price fetch is retried once after this
NO_PRICES_KIND = "no_prices"  # AiService's refusal kind for OpenRouter before its list is loaded
TEST_MAX_TOKENS = 1000  # reasoning models spend output tokens on thinking before the JSON answer
TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
KEY_WORKS_MESSAGE = "The key works."
SERVER_ANSWERED_MESSAGE = "{label} answered."  # a passing Test that sent no key (Ollama, Other without one)
PASTE_FIRST_MESSAGE = "Paste a key first."
KEY_STORE_FAILED_MESSAGE = "Windows could not store the key."
KEY_READ_FAILED_MESSAGE = "Proofline could not read the key from Windows Credential Manager. Details are in the log."
TEST_NOT_SENT_MESSAGE = "Settings did not switch to this provider, so its key was not tested."
MODELS_FAILED_MESSAGE = "Proofline could not load the model list."
KEY_MOVED_MESSAGE = ("The key for Other server was removed because the address changed. "
                     "Save it again for the new address.")
KEY_REMOVE_FAILED_MESSAGE = ("Proofline could not remove the key for the old Other server address, so it will not "
                             "be sent until you save it again.")


def key_test_request() -> AiRequest:
    return AiRequest(TEST_JOB, "Answer as JSON.", "Reply with ok true.", TEST_SCHEMA, TEST_MAX_TOKENS)


class AiSetup(QObject):
    def __init__(
        self,
        page: AiPage,
        service: AiService,
        config_provider: Callable[[], Config],
        keys: KeyStore,
        list_models: Callable = fetch_models,
    ) -> None:
        super().__init__()
        self.page, self.service = page, service
        self._config_provider, self._keys, self._list_models = config_provider, keys, list_models
        self._test_pid: str | None = None  # the provider the running Test was started for
        self._retry_pending = False  # one OpenRouter price retry at a time (see _schedule_retry)
        page.key_save_requested.connect(self._on_save)
        page.key_remove_requested.connect(self._on_remove)
        page.key_test_requested.connect(self._on_test)
        page.provider_chosen.connect(self._on_provider_chosen)
        page.address_saved.connect(self._on_address_saved)
        page.models_refresh_requested.connect(self._refresh_models)
        page.shown.connect(self.refresh)
        page.state_loaded.connect(self.refresh)  # a settings reload may change the shown provider
        service.finished.connect(self._on_finished)
        service.failed.connect(self._on_failed)
        self.refresh()
        config = self._config_provider()
        if config.ai_enabled and config.ai_provider == OPENROUTER_ID:  # its prices are needed before any request
            self._refresh_models(OPENROUTER_ID, retry=True)

    def config_changed(self, previous: Config) -> None:
        """Called by the app after every config change: turning AI on with OpenRouter selected fetches its
        prices, as at startup (the page's provider pick and Refresh fetch on their own)."""
        config = self._config_provider()
        if config.ai_enabled and not previous.ai_enabled and config.ai_provider == OPENROUTER_ID:
            self._refresh_models(OPENROUTER_ID, retry=True)

    def refresh(self) -> None:
        pid = self.page.current_provider()
        self._show_key_state(pid)
        self._show_usage(pid)

    def _show_key_state(self, pid: str) -> None:
        """Show whether pid has a key saved; say so when Credential Manager cannot be read."""
        try:
            saved = self._keys.load(pid) is not None
        except Exception:  # treated as no key, but the page says why
            log.warning("Could not read an API key from Credential Manager", exc_info=True)
            self.page.set_key_saved(pid, False)
            self.page.show_key_result(pid, False, KEY_READ_FAILED_MESSAGE)
            return
        self.page.set_key_saved(pid, saved)

    def _show_usage(self, pid: str) -> None:
        config = self._config_provider()
        self.page.show_usage(usage_text(
            provider(pid), config.ai_address_for(pid), config.ai_model_for(pid),
            self.service.month_totals(), self.service.token_totals(pid), config.ai_monthly_cap_cents,
        ))

    def _on_save(self, pid: str, key: str) -> None:
        if is_insecure_remote(self._config_provider().ai_address_for(pid)):
            self.page.show_key_result(pid, False, KEY_REFUSED_INSECURE)
            return
        try:
            self._keys.save(pid, key)
        except ValueError:
            self.page.show_key_result(pid, False, PASTE_FIRST_MESSAGE)
            return
        except Exception:
            log.warning("Could not store an API key", exc_info=True)
            self.page.show_key_result(pid, False, KEY_STORE_FAILED_MESSAGE)
            return
        if pid == OTHER_ID:  # the key is sent only to the address it is saved for
            self.page.bind_other_key(self._config_provider().ai_other_url)
            self.page.clear_key_status()
        self.service.key_changed(pid)
        self._show_key_state(pid)

    def _on_remove(self, pid: str) -> None:
        if self._delete_key(pid):
            self.service.key_changed(pid)  # a failed removal keeps the key
        self._show_key_state(pid)

    def _delete_key(self, pid: str) -> bool:
        """True when the key was removed (or there was none to remove)."""
        try:
            self._keys.delete(pid)
        except Exception:
            log.warning("Could not remove an API key", exc_info=True)
            return False
        return True

    def _on_test(self, pid: str) -> None:
        if self.service.provider().id != pid:  # Settings has not switched yet: never test another key
            self.page.show_key_result(pid, False, TEST_NOT_SENT_MESSAGE)
            return
        if self.service.busy:  # refused: the running Test keeps its provider slot
            self.page.show_key_result(pid, False, BUSY_MESSAGE)
            return
        self._test_pid = pid
        self.service.submit(key_test_request())

    def _on_finished(self, request: AiRequest, result: object) -> None:
        if request.job == TEST_JOB:
            pid, self._test_pid = self._test_pid, None
            if pid is not None:
                self.page.show_key_result(pid, True, self._test_passed_message(pid))
        self._show_usage(self.page.current_provider())

    def _test_passed_message(self, pid: str) -> str:
        spec = provider(pid)
        if spec.key == "required":
            return KEY_WORKS_MESSAGE
        if spec.key == "optional" and self._sent_key(pid):
            return KEY_WORKS_MESSAGE
        return SERVER_ANSWERED_MESSAGE.format(label=spec.label)

    def _sent_key(self, pid: str) -> bool:
        """True when a request to pid carries its saved key."""
        if pid == OTHER_ID and not self._config_provider().other_key_applies():
            return False
        try:
            return self._keys.load(pid) is not None
        except Exception:  # treated as no key
            log.warning("Could not read an API key from Credential Manager", exc_info=True)
            return False

    def _on_failed(self, request: AiRequest, message: str, kind: str) -> None:
        if request.job == TEST_JOB:
            pid, self._test_pid = self._test_pid, None
            if pid is not None:
                self.page.show_key_result(pid, False, message)
        if kind == NO_PRICES_KIND:  # the list was not loaded yet, or failed: fetch it again so a retry can work
            self._refresh_models(OPENROUTER_ID)
        self._show_usage(self.page.current_provider())

    def _on_provider_chosen(self, pid: str) -> None:
        self._show_key_state(pid)
        self._show_usage(pid)
        if pid == OPENROUTER_ID:
            self._refresh_models(pid)

    def _on_address_saved(self, pid: str, previous: str, address: str) -> None:
        # A key saved for one server is never sent to another address. An Other key saved before any
        # address existed is kept but not bound: it is sent only once it is saved again for this address.
        if pid == OTHER_ID and previous and previous != address:
            self._drop_key_for_moved_address(pid)
        elif pid == OTHER_ID and not previous and self._key_unbound():
            self.page.show_key_result(pid, False, RESAVE_KEY_TEXT)
        self._refresh_models(pid)
        self._show_usage(pid)

    def _key_unbound(self) -> bool:
        """True when a key is saved for Other but is not bound to the address Other uses now."""
        try:
            saved = self._keys.load(OTHER_ID) is not None
        except Exception:  # an unreadable key store: nothing to tell the user about a key
            log.warning("Could not read the Other server's API key", exc_info=True)
            return False
        return saved and not self._config_provider().other_key_applies()

    def _drop_key_for_moved_address(self, pid: str) -> None:
        try:
            had_key = self._keys.load(pid) is not None
            self._keys.delete(pid)
        except Exception:
            log.warning("Could not remove an API key when its address changed", exc_info=True)
            self.page.bind_other_key("")  # the key stays stored, but is bound to no address: not sent until saved again
            self._show_key_state(pid)
            self.page.show_key_result(pid, False, KEY_REMOVE_FAILED_MESSAGE)
            return
        self.service.key_changed(pid)
        self._show_key_state(pid)
        if had_key:
            self.page.show_key_result(pid, False, KEY_MOVED_MESSAGE)

    def _address_of(self, pid: str) -> str:
        """The address pid's models come from: the saved one for a local server, else the fixed one."""
        spec = provider(pid)
        return self._config_provider().ai_address_for(pid) if spec.local else spec.base_url

    def _refresh_models(self, pid: str, retry: bool = False) -> None:
        """Fetch pid's model list in the background; nothing for an empty address. retry: a failed fetch is
        retried once after OPENROUTER_RETRY_MS (startup and AI-on fetches for OpenRouter)."""
        if pid not in LIVE_MODEL_PROVIDERS:
            return
        spec = provider(pid)
        address = self._address_of(pid)
        if not address:
            return

        def fetch():
            return self._list_models(spec, address, self._list_key(pid, address))

        run_in_background(fetch, lambda choices: self._on_models(pid, address, choices),
                          lambda exc: self._on_models_failed(pid, address, exc, retry))

    def _list_key(self, pid: str, address: str) -> str | None:
        """The key a model list is fetched with: none for a provider without one, for OpenRouter (its list is
        public), and for an address that is not encrypted; otherwise the provider's saved key."""
        if provider(pid).key == "none" or pid == OPENROUTER_ID or is_insecure_remote(address):
            return None
        if pid == OTHER_ID and not self._config_provider().other_key_applies():
            return None
        return self._keys.load(pid)

    def _still_current(self, pid: str, address: str) -> bool:
        """False when the address was changed while a list was being fetched for it."""
        return self._address_of(pid) == address

    def _on_models(self, pid: str, address: str, choices: tuple[ModelChoice, ...]) -> None:
        if not self._still_current(pid, address):  # the old server's models are dropped
            return
        self.page.set_model_choices(pid, choices)
        if pid == OPENROUTER_ID:
            self.service.set_live_prices(pid, tuple(c.price for c in choices if c.price is not None))

    def _on_models_failed(self, pid: str, address: str, exc: Exception, retry: bool = False) -> None:
        if not self._still_current(pid, address):
            return
        if retry and pid == OPENROUTER_ID:
            self._schedule_retry()
        if isinstance(exc, AiError):
            self.page.show_models_status(pid, exc.message)
            return
        log.warning("Could not load a model list (%s)", type(exc).__name__)
        self.page.show_models_status(pid, MODELS_FAILED_MESSAGE)

    def _schedule_retry(self) -> None:
        """Retry OpenRouter's prices once, later; a retry already waiting is kept, so there is never more than one."""
        if self._retry_pending:
            return
        self._retry_pending = True
        QTimer.singleShot(OPENROUTER_RETRY_MS, self._run_retry)

    def _run_retry(self) -> None:
        self._retry_pending = False
        config = self._config_provider()
        if config.ai_enabled and config.ai_provider == OPENROUTER_ID:  # the retry is not itself retried
            self._refresh_models(OPENROUTER_ID)
