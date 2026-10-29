"""AI Find more issues, Rewrite for clarity and Change tone: one request at a time for the focused
field, results shown as AI matches.

IssueFinder sends the whole field text through AiService when the user clicks one of those in
the issues popup, shows progress and errors in the popup's AI status line, and hands the findings
to the overlay controller. An answer is dropped when the field's text changed, focus left the
field, AI became unavailable, or the user cancelled; a cancelled request cannot be stopped once
sent, and AiService still records its cost. Closing the popup does not cancel: the status is kept
and shown again when the popup reopens for the same text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject

from proofline.ai_client import AiRequest, AiResult
from proofline.ai_jobs import find_issues_request, issue_matches
from proofline.ai_rewrite import rewrite_outcome, rewrite_request
from proofline.ai_service import AiService
from proofline.lt_client import Match
from proofline.overlay_widgets import IssuesPopup
from proofline.rephrase import CANCELLED_BUSY_MESSAGE, RETRY_KINDS
from proofline.text_snapshot import FieldSnapshot

log = logging.getLogger(__name__)

WAITING_TEXT = "Asking the AI..."
NOTHING_FOUND_MESSAGE = "The AI found nothing more."
NO_CHANGES_MESSAGE = "The AI suggests no changes."
MOSTLY_CHANGED_MESSAGE = "This rewrite changes most of the text. Check each change."
SKIPPED_MESSAGE = "{count} change(s) across a line break are not shown."
FIND = "find"  # the job of a request; a rewrite style id otherwise
TEXT_TOO_LONG_MESSAGE = "This text is too long for AI (over 8,000 characters)."

Deliver = Callable[[FieldSnapshot, tuple[Match, ...]], None]


class IssueFinder(QObject):
    def __init__(self, service: AiService, popup: IssuesPopup, deliver: Deliver) -> None:
        super().__init__()
        self._service = service
        self._popup = popup
        self._deliver = deliver
        self._snapshot: FieldSnapshot | None = None
        self._request: AiRequest | None = None
        self._job = FIND
        self._cancelled_running: AiRequest | None = None  # sent, cancelled, not answered yet
        self._status: tuple[str, bool, bool] | None = None  # message, cancel, retry; for self._snapshot
        service.finished.connect(self._on_finished)
        service.failed.connect(self._on_failed)
        popup.ai_cancel_requested.connect(self._end)
        popup.ai_retry_requested.connect(self._retry)
        popup.shown.connect(self._restore_status)

    @property
    def active(self) -> bool:
        return self._request is not None

    def start(self, snapshot: FieldSnapshot) -> None:
        """Find more issues: show "Asking the AI..." with Cancel, then send the field text."""
        log.info("Find more issues requested (%d characters)", len(snapshot.text))
        self._send(snapshot, FIND, find_issues_request(snapshot.text))

    def start_rewrite(self, snapshot: FieldSnapshot, style_id: str) -> None:
        """Rewrite for clarity or Change tone (style_id from ai_rewrite.STYLES), shown as change rows."""
        log.info("Rewrite (%s) requested (%d characters)", style_id, len(snapshot.text))
        self._send(snapshot, style_id, rewrite_request(style_id, snapshot.text))

    def _send(self, snapshot: FieldSnapshot, job: str, request: AiRequest) -> None:
        self._end()
        self._snapshot, self._job = snapshot, job
        self._show(WAITING_TEXT, cancel=True)
        self._request = request
        self._service.submit(request)  # a refusal arrives through failed, inside this call

    def on_field_changed(self, snapshot: FieldSnapshot | None) -> None:
        """Forget the request and its status when focus left the field or its text changed."""
        current = self._snapshot
        if current is None:
            return
        if snapshot is None or (snapshot.field_id, snapshot.text) != (current.field_id, current.text):
            self._end()
            self._snapshot = None

    def _on_finished(self, request: AiRequest, result: AiResult) -> None:
        if not self._owns(request):
            return
        snapshot = self._snapshot
        if snapshot is None or not self._service.available():  # AI turned off or key removed while waiting
            self._end()
            return
        if self._job == FIND:
            self._show_found(snapshot, issue_matches(result, snapshot.text), NOTHING_FOUND_MESSAGE)
            return
        outcome = rewrite_outcome(result, snapshot.text, self._job)
        notes = [MOSTLY_CHANGED_MESSAGE] if outcome.mostly_changed and outcome.matches else []
        if outcome.skipped:
            notes.append(SKIPPED_MESSAGE.format(count=outcome.skipped))
        self._show_found(snapshot, outcome.matches, NO_CHANGES_MESSAGE, " ".join(notes))

    def _show_found(self, snapshot: FieldSnapshot, matches: tuple[Match, ...], empty: str, note: str = "") -> None:
        """Hand matches to the overlay with note in the status line (none when empty), or say empty."""
        if not matches:
            self._show(note or empty)
            return
        if note:
            self._show(note)
        else:
            self._status = None
            self._popup.clear_ai_status()
        self._deliver(snapshot, matches)

    def _on_failed(self, request: AiRequest, message: str, kind: str) -> None:
        if not self._owns(request):
            return
        if kind == "too_long":
            message = TEXT_TOO_LONG_MESSAGE
        elif kind == "busy" and self._cancelled_running is not None:
            message = CANCELLED_BUSY_MESSAGE
        self._show(message, retry=kind in RETRY_KINDS)

    def _owns(self, request: AiRequest) -> bool:
        """True for the answer to this finder's current request; consumes it."""
        if request is self._cancelled_running:
            self._cancelled_running = None
        if request is not self._request:
            return False
        self._request = None
        return True

    def _show(self, message: str, cancel: bool = False, retry: bool = False) -> None:
        self._status = (message, cancel, retry)
        self._popup.show_ai_status(message, cancel=cancel, retry=retry)

    def _restore_status(self) -> None:
        """Show the status again when the popup reopens; a waiting line only while its request is live."""
        if self._status is None:
            return
        message, cancel, retry = self._status
        if message == WAITING_TEXT and not self._waiting():
            self._status = None  # the request ended, or AI was turned off, while the popup was closed
            return
        self._popup.show_ai_status(message, cancel=cancel, retry=retry)

    def _waiting(self) -> bool:
        return self._request is not None and self._service.available()

    def _retry(self) -> None:
        if self._snapshot is None:
            return
        if self._job == FIND:
            self.start(self._snapshot)
        else:
            self.start_rewrite(self._snapshot, self._job)

    def _end(self) -> None:
        """Drop the running request (its answer is ignored when it arrives) and clear the status."""
        if self._request is not None:
            self._cancelled_running = self._request
        self._request = None
        self._status = None
        self._popup.clear_ai_status()
