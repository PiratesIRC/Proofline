"""AI Rephrase: one sentence at a time, shown in the card, applied through the checked replace path.

The Rephraser holds the card while it waits so the flagged-word card logic leaves it alone, sends
only the sentence through AiService, and drops an answer that no longer applies: the field's text
changed, focus left the field, AI was turned off, or the user cancelled. A cancelled request
cannot be stopped once sent; its answer is ignored and AiService still records its cost.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QRect

from proofline.ai_client import AiRequest, AiResult
from proofline.ai_jobs import rephrase_options, rephrase_request
from proofline.ai_service import AiService
from proofline.issue_card import IssueCard
from proofline.replace_request import ReplaceRequest
from proofline.text_snapshot import FieldSnapshot

log = logging.getLogger(__name__)

NO_OPTIONS_MESSAGE = "The AI found no better wording."
SENTENCE_TOO_LONG_MESSAGE = "This sentence is too long to rephrase (over 8,000 characters)."
CANCELLED_BUSY_MESSAGE = "The cancelled request is still finishing. Try again in a moment."
CARET_UNKNOWN_MESSAGE = "Proofline can't find the caret in this field."
RETRY_KINDS = frozenset({"timeout", "network", "server", "rate_limit", "bad_response", "busy", "error"})


@dataclass(frozen=True)
class RephraseTarget:
    snapshot: FieldSnapshot
    start: int  # Python indices of the sentence in snapshot.text
    end: int
    anchor: QRect  # logical screen rectangle the card opens under
    bounds: QRect  # the screen's available area
    accent: str

    @property
    def sentence(self) -> str:
        return self.snapshot.text[self.start:self.end]


class Rephraser(QObject):
    def __init__(
        self,
        service: AiService,
        card: IssueCard,
        hold_card: Callable[[bool], None],
        replace: Callable[[ReplaceRequest], None],
    ) -> None:
        super().__init__()
        self._service = service
        self.card = card
        self._hold_card = hold_card
        self._replace = replace
        self._target: RephraseTarget | None = None
        self._request: AiRequest | None = None
        self._cancelled_running: AiRequest | None = None  # sent, cancelled, not answered yet
        self._message_field: tuple[int, ...] | None = None  # field a caret message belongs to
        self._held = False
        service.finished.connect(self._on_finished)
        service.failed.connect(self._on_failed)
        card.rephrase_chosen.connect(self._on_chosen)
        card.rephrase_cancelled.connect(self._end)
        card.rephrase_retry.connect(self._retry)

    @property
    def active(self) -> bool:
        return self._held

    def start(self, target: RephraseTarget) -> None:
        """Show the waiting card under target.anchor, then send the sentence.

        A press while a request is still running is ignored: the running request keeps going and
        its answer is shown. Sending a second one would bill the first answer and drop it.
        """
        if self._request is not None:
            log.debug("Rephrase shortcut ignored: a request is already running")
            return
        self._end(release=False)
        self._target = target
        log.info("Rephrase requested (%d characters)", target.end - target.start)
        self._hold(True)
        self.card.show_waiting(target.sentence, target.anchor, target.bounds, target.accent)
        self._request = rephrase_request(target.sentence)
        self._service.submit(self._request)  # a refusal arrives through failed, inside this call

    def show_message_at(
        self, anchor: QRect, bounds: QRect, accent: str, message: str, snapshot: FieldSnapshot
    ) -> None:
        """A one-line message in the card with Close, with nothing sent; it closes when focus leaves snapshot's field."""
        if self._request is not None:  # a shortcut press during a running rephrase is ignored, as in start()
            log.debug("Caret message skipped: a rephrase request is already running")
            return
        self._end(release=False)
        self._message_field = snapshot.field_id
        self._hold(True)
        self.card.show_message(message, retry=False, anchor=anchor, bounds=bounds, accent=accent)

    def on_field_changed(self, snapshot: FieldSnapshot | None) -> None:
        """End the rephrase when focus left the field or its text changed; a caret move keeps it."""
        target = self._target
        if target is None:
            if self._message_field is not None and (snapshot is None or snapshot.field_id != self._message_field):
                self._end()
            return
        if snapshot is None or (snapshot.field_id, snapshot.text) != (target.snapshot.field_id, target.snapshot.text):
            self._end()

    def _on_finished(self, request: AiRequest, result: AiResult) -> None:
        if request is self._cancelled_running:
            self._cancelled_running = None
        if request is not self._request or self._target is None:
            return
        self._request = None
        if not self._service.available():  # AI turned off or key removed while waiting
            self._end()
            return
        options = rephrase_options(result, self._target.sentence)
        if options:
            self.card.show_options(options, self._target.sentence)
        else:
            self.card.show_message(NO_OPTIONS_MESSAGE, retry=False)

    def _on_failed(self, request: AiRequest, message: str, kind: str) -> None:
        if request is self._cancelled_running:
            self._cancelled_running = None
        if request is not self._request or self._target is None:
            return
        self._request = None
        if kind == "too_long":
            message = SENTENCE_TOO_LONG_MESSAGE
        elif kind == "busy" and self._cancelled_running is not None:
            message = CANCELLED_BUSY_MESSAGE
        self.card.show_message(message, retry=kind in RETRY_KINDS)

    def _on_chosen(self, wording: str) -> None:
        target = self._target
        if target is None:
            return
        self._end()
        snap = target.snapshot
        log.info("Rephrase chosen (%d characters replaced)", target.end - target.start)
        self._replace(ReplaceRequest(snap.field_id, snap.window_title, snap.text, target.start,
                                     target.end - target.start, target.sentence, wording))

    def _retry(self) -> None:
        if self._target is not None:
            self.start(self._target)

    def _end(self, release: bool = True) -> None:
        """Forget the rephrase; an answer still on its way is dropped when it arrives."""
        if self._request is not None:
            self._cancelled_running = self._request
        self._request = None
        self._target = None
        self._message_field = None
        if release:
            self.card.hide()
            self._hold(False)

    def _hold(self, held: bool) -> None:
        if held != self._held:
            self._held = held
            self._hold_card(held)
