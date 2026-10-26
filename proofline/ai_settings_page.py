"""The AI page of the Settings window: on/off, the Claude API key, model, spending limit, usage.

The switch, model and limit save instantly like every other setting. The key has explicit
Save, Test and Remove buttons; the app stores it in Credential Manager (ai_keys) and the page
never shows a saved key again.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QPushButton

from proofline.ai_prices import MODELS
from proofline.ai_usage import Totals
from proofline.config import AI_CAP_CENTS_RANGE, Config
from proofline.settings_pages import (
    COMBO_WIDTH,
    URL_WIDTH,
    Page,
    _accent_button,
    _link_label,
    _set_combo_data,
    _switch,
)
from proofline.ui_kit import SettingCard, set_object_name

CENTS_PER_DOLLAR = 100
CAP_STEP_DOLLARS = 0.10
PRIVACY_URL = "https://privacy.anthropic.com/"
PRIVACY_TEXT = (
    "When you ask for an AI suggestion, Proofline sends that text to Anthropic's Claude API with "
    "your key. Nothing is sent otherwise."
)
PRIVACY_LINK_TEXT = "How Anthropic uses API data"
KEY_DESCRIPTION = "From console.anthropic.com. Kept in Windows Credential Manager, not in the settings file"
KEY_SAVED_TEXT = "Key saved"
TESTING_TEXT = "Testing the key..."
SWITCH_DESCRIPTION = "Rewords a sentence with Claude, only when you ask"
CAP_DESCRIPTION = "AI requests stop for the month once the recorded cost would pass this"


def model_label(model) -> str:
    return f"{model.label} (${model.input_per_million:.2f} / ${model.output_per_million:.2f} per million tokens)"


def totals_text(totals: Totals, cap_cents: int) -> str:
    requests = "request" if totals.requests_month == 1 else "requests"
    return (f"Today ${totals.today:.4f} · This month ${totals.month:.4f} of "
            f"${cap_cents / CENTS_PER_DOLLAR:.2f} · {totals.requests_month} {requests}")


class AiPage(Page):
    title = "AI"
    key_save_requested = pyqtSignal(str)
    key_remove_requested = pyqtSignal()
    key_test_requested = pyqtSignal()
    shown = pyqtSignal()  # the app refreshes the key state and usage totals

    def __init__(self) -> None:
        super().__init__()
        self._cap_cents = Config().ai_monthly_cap_cents
        self._key_saved = False
        self.enabled_switch = _switch("Use AI suggestions", lambda on: self._emit(ai_enabled=on))
        self._build_key_controls()
        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(COMBO_WIDTH)
        for model in MODELS:
            self.model_box.addItem(model_label(model), model.model_id)
        self.model_box.currentIndexChanged.connect(lambda: self._emit(ai_model=self.model_box.currentData()))
        self.cap_box = QDoubleSpinBox()
        low, high = AI_CAP_CENTS_RANGE
        self.cap_box.setRange(low / CENTS_PER_DOLLAR, high / CENTS_PER_DOLLAR)
        self.cap_box.setSingleStep(CAP_STEP_DOLLARS)
        self.cap_box.setDecimals(2)
        self.cap_box.setPrefix("$")
        self.cap_box.valueChanged.connect(
            lambda value: self._emit(ai_monthly_cap_cents=round(value * CENTS_PER_DOLLAR)))
        self.usage_label = QLabel("")
        self.usage_label.setObjectName("cardDescription")
        self._build_cards()

    def _build_key_controls(self) -> None:
        self.key_box = QLineEdit()
        self.key_box.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_box.setPlaceholderText("sk-ant-...")
        self.key_box.setMinimumWidth(URL_WIDTH)
        self.key_saved_label = QLabel(KEY_SAVED_TEXT)
        self.save_button = _accent_button("Save")
        self.save_button.clicked.connect(lambda: self.key_save_requested.emit(self.key_box.text()))
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._on_test)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.key_remove_requested.emit)
        self.key_status = QLabel("")
        self.key_status.setObjectName("cardDescription")
        self.key_status.setWordWrap(True)
        self.privacy_label = QLabel(PRIVACY_TEXT)
        self.privacy_label.setObjectName("cardDescription")
        self.privacy_label.setWordWrap(True)
        # Its own label: a link inside a style-sheet-styled label ignores the accent link colour.
        self.privacy_link = _link_label(PRIVACY_URL, PRIVACY_LINK_TEXT)

    def _build_cards(self) -> None:
        self._group("Claude")
        self._card(SettingCard("Use AI suggestions", SWITCH_DESCRIPTION, self.enabled_switch,
                               keywords="ai claude anthropic"))
        self._card(SettingCard("Claude API key", KEY_DESCRIPTION, self.key_box, self.key_saved_label,
                               self.save_button, self.test_button, self.remove_button,
                               keywords="ai anthropic api key"))
        self._layout.addWidget(self.key_status)
        self._layout.addWidget(self.privacy_label)
        self._layout.addWidget(self.privacy_link)
        self._group("Model and spending")
        self._card(SettingCard("Model", "Haiku is the fastest and cheapest", self.model_box, keywords="ai claude"))
        self._card(SettingCard("Monthly spending limit", CAP_DESCRIPTION, self.cap_box,
                               keywords="ai cost cap budget money"))
        self._layout.addWidget(self.usage_label)
        self._finish()
        self.key_status.hide()
        self.set_key_saved(False)

    def _load(self, config: Config) -> None:
        self._cap_cents = config.ai_monthly_cap_cents
        self.enabled_switch.setChecked(config.ai_enabled)
        _set_combo_data(self.model_box, config.ai_model, config.ai_model)
        self.cap_box.setValue(config.ai_monthly_cap_cents / CENTS_PER_DOLLAR)

    def set_key_saved(self, saved: bool) -> None:
        """Show the key box (no key) or "Key saved" with Remove (key saved); never the key itself."""
        self._key_saved = saved
        if saved:
            self.key_box.clear()
        self.key_box.setVisible(not saved)
        self.save_button.setVisible(not saved)
        self.key_saved_label.setVisible(saved)
        self.remove_button.setVisible(saved)
        self.test_button.setEnabled(saved)

    def show_key_result(self, ok: bool, message: str) -> None:
        self.test_button.setEnabled(self._key_saved)
        set_object_name(self.key_status, "statusOk" if ok else "statusError")
        self.key_status.setText(message)
        self.key_status.show()

    def show_totals(self, totals: Totals) -> None:
        self.usage_label.setText(totals_text(totals, self._cap_cents))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.shown.emit()

    def _on_test(self) -> None:
        self.test_button.setEnabled(False)
        set_object_name(self.key_status, "cardDescription")
        self.key_status.setText(TESTING_TEXT)
        self.key_status.show()
        self.key_test_requested.emit()
