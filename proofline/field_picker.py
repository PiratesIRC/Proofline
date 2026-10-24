"""'Add a text field' helper: the user clicks into any field, we explain whether it can
be checked, and offer to always check that field or app."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFontDatabase, QGuiApplication, QShowEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from proofline.config import Config, saveable_signature
from proofline.text_snapshot import FocusResult

log = logging.getLogger(__name__)

WINDOW_TITLE = "Add a text field"
INSTRUCTIONS = (
    "1. Click the app window you want to use.\n"
    "2. Click inside the text box you want checked.\n"
    "This window stays on top and explains what it finds."
)
WAITING = "Waiting for you to click into a text box…"
IGNORED_REASONS = frozenset({"focus is in this app", "no focused element", "checking paused"})
FILTER_REASON_PREFIXES = ("not a text control", "address bar", "numeric field", "sensitive field")
NO_TEXT_PATTERNS = "none"
DETAILS_HEIGHT = 130


@dataclass(frozen=True)
class Assessment:
    verdict: str
    explanation: str
    can_add_field: bool = False
    can_add_app: bool = False


def assess(result: FocusResult, config: Config) -> Assessment | None:
    """Explain a captured field. None means 'ignore this capture' (e.g. our own window)."""
    reason = result.reason
    if not result.process_name or reason in IGNORED_REASONS:
        return None
    app = result.process_name
    if reason.startswith("ok"):
        if config.is_disabled_for(app, result.window_title) and not config.is_custom_field(result.signature):
            return Assessment(
                "Turned off here",
                f"This is a text box, but checking is turned off for {app} or this window "
                "by your exclusions.",
                can_add_app=True,
            )
        return Assessment("Already checked ✓", "This text box is already being checked.")
    if reason == "password field":
        return Assessment("Password field", "Password fields are never checked.")
    if reason.startswith("app runs as administrator"):
        return Assessment(
            "Can't read this app",
            f"{app} runs as administrator, and Windows blocks normal apps from reading it. "
            "Run Proofline as administrator to check it.",
        )
    if reason == "read-only":
        return Assessment("Read-only", "This field can't be edited, so there is nothing to correct.")
    if result.patterns == NO_TEXT_PATTERNS or reason.startswith(("no Text or Value", "dropdown")):
        hint = getattr(result.hint, "message", "")
        return Assessment(
            "Text isn't available",
            f"{app} doesn't share this field's text with other programs, so it can't be checked. "
            + hint,
        )
    if reason.startswith(FILTER_REASON_PREFIXES):
        return Assessment(
            "Skipped by a rule",
            f"This field was skipped ({reason}), but its text can be read. "
            "Add it to always check this kind of field.",
            can_add_field=True,
        )
    return Assessment("Not supported", f"This field can't be checked: {reason}.")


def details_text(result: FocusResult) -> str:
    """Plain-text diagnostics for 'Copy details' (no field contents)."""
    return "\n".join(
        (
            f"App:          {result.process_name}",
            f"Window:       {result.window_title}",
            f"Element:      {result.description}",
            f"Signature:    {result.signature}",
            f"Text access:  {result.patterns or 'unknown'}",
            f"Result:       {result.reason}",
        )
    )


class FieldPickerDialog(QDialog):
    capture_started = pyqtSignal()
    capture_stopped = pyqtSignal()
    add_field_requested = pyqtSignal(str)  # field signature
    add_app_requested = pyqtSignal(str)  # process name

    def __init__(self, config_provider: Callable[[], Config]) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(460)
        self._config_provider = config_provider
        self._result: FocusResult | None = None

        self._verdict = QLabel(WAITING)
        font = self._verdict.font()
        font.setBold(True)
        self._verdict.setFont(font)
        self._explanation = QLabel()
        self._explanation.setWordWrap(True)
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._details.setFixedHeight(DETAILS_HEIGHT)

        self._add_field_button = QPushButton("Always check this field")
        self._add_field_button.clicked.connect(self._add_field)
        self._add_app_button = QPushButton("Always check this app")
        self._add_app_button.clicked.connect(self._add_app)
        self._copy_button = QPushButton("Copy details")
        self._copy_button.clicked.connect(self._copy_details)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        for button in (self._add_field_button, self._add_app_button, self._copy_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(INSTRUCTIONS))
        layout.addWidget(self._verdict)
        layout.addWidget(self._explanation)
        layout.addWidget(self._details)
        layout.addLayout(buttons)
        self._show_result(None, None)

    def open_picker(self) -> None:
        self._show_result(None, None)
        self.show()
        self.raise_()
        self.activateWindow()

    def on_captured(self, result: FocusResult) -> None:
        assessment = assess(result, self._config_provider())
        if assessment is None:
            return
        log.info("Field picker captured %s -> %s", result.signature, result.reason)
        self._show_result(result, assessment)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.capture_started.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.capture_stopped.emit()
        super().closeEvent(event)

    def _show_result(self, result: FocusResult | None, assessment: Assessment | None) -> None:
        self._result = result
        self._verdict.setText(assessment.verdict if assessment else WAITING)
        self._explanation.setText(assessment.explanation if assessment else "")
        self._details.setPlainText(details_text(result) if result else "")
        self._add_field_button.setEnabled(bool(assessment and assessment.can_add_field))
        self._add_app_button.setEnabled(bool(assessment and assessment.can_add_app))
        self._copy_button.setEnabled(result is not None)

    def _add_field(self) -> None:
        if self._result is not None:
            self.add_field_requested.emit(saveable_signature(self._result.signature))
            self._confirm_added("this field")

    def _add_app(self) -> None:
        if self._result is not None:
            self.add_app_requested.emit(self._result.process_name)
            self._confirm_added(self._result.process_name)

    def _confirm_added(self, what: str) -> None:
        self._add_field_button.setEnabled(False)
        self._add_app_button.setEnabled(False)
        self._verdict.setText("Added ✓")
        self._explanation.setText(
            f"Proofline will now check {what}. Click into the text box again to see the badge."
        )

    def _copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self._details.toPlainText())
        self._explanation.setText("Details copied. Paste them into your issue report.")
