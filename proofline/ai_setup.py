"""Connects the Settings AI page to the key store and the AI request service.

Kept out of app.py so it can be tested with a stand-in key store. The Test button sends one
small request through AiService, so it follows the same rules (AI on, key saved, spending
limit) and is recorded in the usage ledger like any other request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject

from proofline.ai_client import AiRequest
from proofline.ai_service import AiService
from proofline.ai_settings_page import AiPage

log = logging.getLogger(__name__)

TEST_JOB = "test"
TEST_MAX_TOKENS = 50
TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
KEY_WORKS_MESSAGE = "The key works."
PASTE_FIRST_MESSAGE = "Paste a key first."
KEY_STORE_FAILED_MESSAGE = "Windows could not store the key."


def key_test_request() -> AiRequest:
    return AiRequest(TEST_JOB, "Answer as JSON.", "Reply with ok true.", TEST_SCHEMA, TEST_MAX_TOKENS)


class AiSetup(QObject):
    def __init__(
        self,
        page: AiPage,
        service: AiService,
        save_key: Callable[[str], None],
        delete_key: Callable[[], None],
        load_key: Callable[[], str | None],
    ) -> None:
        super().__init__()
        self.page, self.service = page, service
        self._save_key, self._delete_key, self._load_key = save_key, delete_key, load_key
        page.key_save_requested.connect(self._on_save)
        page.key_remove_requested.connect(self._on_remove)
        page.key_test_requested.connect(lambda: service.submit(key_test_request()))
        page.shown.connect(self.refresh)
        service.finished.connect(self._on_finished)
        service.failed.connect(self._on_failed)
        self.refresh()

    def refresh(self) -> None:
        self.page.set_key_saved(self._has_key())
        self.page.show_totals(self.service.month_totals())

    def _has_key(self) -> bool:
        try:
            return self._load_key() is not None
        except Exception:  # Credential Manager unavailable: treat as no key
            log.warning("Could not read the API key from Credential Manager", exc_info=True)
            return False

    def _on_save(self, key: str) -> None:
        try:
            self._save_key(key)
        except ValueError:
            self.page.show_key_result(False, PASTE_FIRST_MESSAGE)
            return
        except Exception:
            log.warning("Could not store the API key", exc_info=True)
            self.page.show_key_result(False, KEY_STORE_FAILED_MESSAGE)
            return
        self.service.key_changed()
        self.page.set_key_saved(self._has_key())

    def _on_remove(self) -> None:
        try:
            self._delete_key()
        except Exception:
            log.warning("Could not remove the API key", exc_info=True)
        self.service.key_changed()
        self.page.set_key_saved(self._has_key())

    def _on_finished(self, request: AiRequest, result: object) -> None:
        if request.job == TEST_JOB:
            self.page.show_key_result(True, KEY_WORKS_MESSAGE)
        self.page.show_totals(self.service.month_totals())

    def _on_failed(self, request: AiRequest, message: str, _kind: str) -> None:
        if request.job == TEST_JOB:
            self.page.show_key_result(False, message)
        self.page.show_totals(self.service.month_totals())
