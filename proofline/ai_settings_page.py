"""The AI page of the Settings window: on/off, provider, its key or address, model, spending limit, usage.

The switch, provider, model and limit save instantly like every other setting. Each provider keeps
its own key in Credential Manager (ai_keys), with explicit Save, Test and Remove buttons; Ollama and
Other take an address with an explicit Save and Test. The page never shows a saved key again. The page
only shows state: AiSetup reads keys, tests them and fills the usage line and model lists.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QPushButton

from proofline.ai_model_list import ModelChoice
from proofline.ai_page_text import (
    ADDRESS_DESCRIPTION,
    KEY_PLACEHOLDER,
    OTHER_MODEL_TEXT,
    UNTESTED_NOTE,
    estimated_price_text,
    insecure_text,
    key_description,
    key_title,
    privacy_text,
    provider_item_text,
    warning_text,
)
from proofline.ai_prices import models_for
from proofline.ai_providers import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    is_valid_model_name,
    normalize_ai_address,
    provider,
)
from proofline.ai_service import OPENROUTER_ID
from proofline.config import AI_CAP_CENTS_RANGE, OLLAMA_ID, OTHER_ID, Config
from proofline.settings_pages import (
    COMBO_WIDTH,
    URL_WIDTH,
    Page,
    _accent_button,
    _link_label,
    _switch,
)
from proofline.ui_kit import SettingCard, set_link_text, set_object_name

CENTS_PER_DOLLAR = 100
CAP_STEP_DOLLARS = 0.10
SWITCH_DESCRIPTION = "Rewords a sentence or finds more issues with the AI provider you choose, only when you ask"
PROVIDER_DESCRIPTION = "Each provider keeps its own key"
PROVIDER_KEYWORDS = "ai provider " + " ".join(spec.label for spec in PROVIDERS).casefold()
PROVIDER_GROUP_TEXT = "Provider"
SPENDING_GROUP_TEXT = "Model and spending"  # cloud providers
USAGE_GROUP_TEXT = "Model and usage"  # Ollama and Other
KEY_SAVED_TEXT = "Key saved"
TESTING_TEXT = "Testing the key..."
CAP_DESCRIPTION = "AI requests stop for the month once the recorded cost would pass this"
MODEL_DESCRIPTION = {DEFAULT_PROVIDER: "Haiku is the fastest and cheapest"}
ADDRESS_FIELDS = {OLLAMA_ID: "ai_ollama_url", OTHER_ID: "ai_other_url"}  # the Config field each address saves to
LIVE_MODEL_PROVIDERS = (OPENROUTER_ID, OLLAMA_ID, OTHER_ID)  # their model lists come from the server
OTHER_MODEL_DATA = None  # the model list entry that opens the typed-name box
TYPED_MODEL_HINT = "Use letters, digits and . - _ : / only, up to 200 characters."
PRIVACY_LINK_TEXT = "How {label} uses API data"
SAVE_ADDRESS_FIRST = "Save the address first"


def model_label(model) -> str:
    return f"{model.label} (${model.input_per_million:.2f} / ${model.output_per_million:.2f} per million tokens)"


def _choice_label(choice: ModelChoice) -> str:
    return model_label(choice.price) if choice.price is not None else choice.label


def _note_label() -> QLabel:
    """A small wrapped line in the card-description style; hidden until it has text."""
    label = QLabel("")
    label.setObjectName("cardDescription")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)  # some text is the server's own words: never read as HTML
    return label


def _set_note(label: QLabel, text: str) -> None:
    label.setText(text)
    label.setVisible(bool(text))


def _group_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("groupTitle")
    return label


class AiPage(Page):
    title = "AI"
    key_save_requested = pyqtSignal(str, str)  # provider, the typed key
    key_remove_requested = pyqtSignal(str)  # provider
    key_test_requested = pyqtSignal(str)  # provider
    provider_chosen = pyqtSignal(str)  # the user picked a provider; AiSetup shows its key and models
    address_saved = pyqtSignal(str, str, str)  # provider, the address before the save ("" if none), the address now
    models_refresh_requested = pyqtSignal(str)  # provider
    shown = pyqtSignal()  # the app refreshes the key state and usage totals
    state_loaded = pyqtSignal()  # after every load(): the shown provider may have changed, so its state is re-read

    def __init__(self) -> None:
        super().__init__()
        self._config = Config()
        self._key_saved = False
        self._choices: dict[str, tuple[ModelChoice, ...]] = {}
        self._address_pid: str | None = None
        self._model_pid: str | None = None  # the provider the model drop-down was built for
        self._other_open = False  # the user picked "Other model..." and has not picked a listed model since
        self._test_pid: str | None = None  # the provider whose key Test is running; None when no test runs
        self.enabled_switch = _switch("Use AI suggestions", lambda on: self._emit(ai_enabled=on))
        self._build_provider_controls()
        self._build_key_controls()
        self._build_address_controls()
        self._build_model_controls()
        self._build_privacy_controls()
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

    def _build_provider_controls(self) -> None:
        self.provider_box = QComboBox()
        self.provider_box.setMinimumWidth(COMBO_WIDTH)
        for spec in PROVIDERS:
            self.provider_box.addItem(provider_item_text(spec), spec.id)
        self.provider_box.activated.connect(self._on_provider_activated)

    def _build_key_controls(self) -> None:
        self.key_box = QLineEdit()
        self.key_box.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_box.setMinimumWidth(URL_WIDTH)
        self.key_saved_label = QLabel(KEY_SAVED_TEXT)
        self.save_button = _accent_button("Save")
        self.save_button.clicked.connect(lambda: self.key_save_requested.emit(self.current_provider(),
                                                                              self.key_box.text()))
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._on_test)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(lambda: self.key_remove_requested.emit(self.current_provider()))
        # Shows key results, and the address errors and results of Ollama and Other.
        self.key_status = _note_label()

    def _build_address_controls(self) -> None:
        self.address_box = QLineEdit()
        self.address_box.setMinimumWidth(URL_WIDTH)
        self.address_box.textChanged.connect(self._sync_address_test)
        self.address_save_button = _accent_button("Save")
        self.address_save_button.clicked.connect(self._on_address_save)
        self.address_test_button = QPushButton("Test")
        self.address_test_button.clicked.connect(self._on_test)

    def _build_model_controls(self) -> None:
        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(COMBO_WIDTH)
        self.model_box.currentIndexChanged.connect(self._on_model_picked)
        self.model_name_box = QLineEdit()
        self.model_name_box.setPlaceholderText("Model name")
        self.model_name_box.setMinimumWidth(URL_WIDTH)
        self.model_name_box.editingFinished.connect(self._on_model_typed)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(lambda: self.models_refresh_requested.emit(self.current_provider()))
        self.estimated_label = _note_label()
        self.model_status = _note_label()

    def _build_privacy_controls(self) -> None:
        self.privacy_label = _note_label()
        self.warning_label = _note_label()
        self.untested_label = _note_label()
        self.insecure_label = _note_label()
        # Its own label: a link inside a style-sheet-styled label ignores the accent link colour.
        self.privacy_link = _link_label("", "")

    def _build_cards(self) -> None:
        self._card(SettingCard("Use AI suggestions", SWITCH_DESCRIPTION, self.enabled_switch,
                               keywords="ai claude anthropic"))
        self._build_provider_group()
        self._build_model_group()
        self._finish()
        for widget in (self.key_status, self.model_name_box, self.estimated_label, self.model_status,
                       self.untested_label, self.warning_label, self.insecure_label, self.privacy_link):
            widget.hide()
        self.set_key_saved(self.current_provider(), False)
        self._sync_provider_widgets()

    def _build_provider_group(self) -> None:
        self.provider_group = _group_title(PROVIDER_GROUP_TEXT)
        self._layout.addWidget(self.provider_group)
        self.provider_card = self._card(SettingCard("AI provider", PROVIDER_DESCRIPTION, self.provider_box,
                                                    keywords=PROVIDER_KEYWORDS))
        spec = provider(self.current_provider())
        self.key_card = self._card(SettingCard(key_title(spec), key_description(spec), self.key_box,
                                               self.key_saved_label, self.save_button, self.test_button,
                                               self.remove_button, keywords="ai api key"))
        self.address_card = self._card(SettingCard("Server address", "", self.address_box,
                                                   self.address_save_button, self.address_test_button,
                                                   keywords="ai address server url"))
        for widget in (self.key_status, self.untested_label, self.privacy_label, self.warning_label,
                       self.insecure_label, self.privacy_link):
            self._layout.addWidget(widget)

    def _build_model_group(self) -> None:
        self.model_group = _group_title(SPENDING_GROUP_TEXT)
        self._layout.addWidget(self.model_group)
        self.model_card = self._card(SettingCard("Model", "", self.model_box, self.refresh_button,
                                                 keywords="ai model"))
        for widget in (self.model_name_box, self.estimated_label, self.model_status):
            self._layout.addWidget(widget)
        self.cap_card = self._card(SettingCard("Monthly spending limit", CAP_DESCRIPTION, self.cap_box,
                                               keywords="ai cost cap budget money"))
        self._layout.addWidget(self.usage_label)

    def current_provider(self) -> str:
        """The provider the page shows: the one chosen in the drop-down."""
        return self.provider_box.currentData()

    def load(self, config: Config) -> None:
        super().load(config)
        self.state_loaded.emit()

    def _load(self, config: Config) -> None:
        self._config = config
        self.enabled_switch.setChecked(config.ai_enabled)
        self.provider_box.setCurrentIndex(self.provider_box.findData(config.ai_provider))
        self._show_address()
        self._fill_models()
        self._sync_provider_widgets()
        self.cap_box.setValue(config.ai_monthly_cap_cents / CENTS_PER_DOLLAR)

    def _on_provider_activated(self, index: int) -> None:
        """The user picked a provider: its key box starts empty, the AiSetup asks for its state."""
        pid = self.provider_box.itemData(index)
        self.provider_box.setCurrentIndex(index)
        self.key_box.clear()
        self._clear_key_status()
        self._show_address()
        self._fill_models()
        self._sync_provider_widgets()
        self._emit(ai_provider=pid)
        self.provider_chosen.emit(pid)

    def filter(self, query: str) -> bool:
        """The settings search; cards the shown provider does not use stay hidden."""
        matched = super().filter(query)
        self._sync_provider_widgets()
        return matched

    def _sync_provider_widgets(self) -> None:
        """Show the cards and wording that fit the shown provider."""
        pid = self.current_provider()
        spec = provider(pid)
        self.key_box.setPlaceholderText(KEY_PLACEHOLDER)  # neutral: a key's format differs by provider
        self.key_card.setVisible(spec.key != "none")
        self.key_card.title_label.setText(key_title(spec))
        self.key_card.set_description(key_description(spec))
        self.address_card.setVisible(pid in ADDRESS_FIELDS)
        self.address_card.set_description(ADDRESS_DESCRIPTION.get(pid, ""))
        self.cap_card.setVisible(spec.priced)
        self.model_group.setText(SPENDING_GROUP_TEXT if spec.priced else USAGE_GROUP_TEXT)
        self.refresh_button.setVisible(pid in LIVE_MODEL_PROVIDERS)
        self.model_card.set_description(MODEL_DESCRIPTION.get(pid, ""))
        self._show_privacy(spec, self._config.ai_address_for(pid), self._config.ai_model_for(pid))

    def _show_privacy(self, spec, address: str, model: str) -> None:
        _set_note(self.privacy_label, privacy_text(spec, address, model))
        _set_note(self.warning_label, warning_text(spec))
        _set_note(self.insecure_label, insecure_text(address))
        _set_note(self.untested_label, "" if spec.tested else UNTESTED_NOTE)
        if spec.privacy_url:
            link = f'<a href="{spec.privacy_url}">{PRIVACY_LINK_TEXT.format(label=spec.label)}</a>'
            set_link_text(self.privacy_link, link)
        self.privacy_link.setVisible(bool(spec.privacy_url))

    def _show_address(self) -> None:
        """Show the shown provider's saved address; keep what the user typed while the provider stays."""
        pid = self.current_provider()
        if pid != self._address_pid:
            self._address_pid = pid
            self.address_box.setText(self._config.ai_address_for(pid))
            self._clear_key_status()
        self._sync_address_test()

    def _sync_address_test(self) -> None:
        """Test checks the saved address, so it waits while the box holds an unsaved edit."""
        unsaved = self.address_box.text().strip() != self._config.ai_address_for(self.current_provider())
        self.address_test_button.setEnabled(not unsaved and not self._testing)
        self.address_test_button.setToolTip(SAVE_ADDRESS_FIRST if unsaved else "")

    def bind_other_key(self, address: str) -> None:
        """Other's saved key belongs to this address (ai_other_key_address); "" binds it to none."""
        self._emit(ai_other_key_address=address)

    def _on_address_save(self) -> None:
        pid = self.current_provider()
        if pid not in ADDRESS_FIELDS:
            return
        try:
            address = normalize_ai_address(self.address_box.text())
        except ValueError as exc:
            self._show_status(str(exc), ok=False)
            return
        previous = self._config.ai_address_for(pid)
        if address != previous:
            self._emit(**{ADDRESS_FIELDS[pid]: address})
        self.address_box.setText(address)
        self._clear_key_status()
        self.address_saved.emit(pid, previous, address)

    def _model_rows(self, pid: str) -> list[tuple[str, str]]:
        """(model id, label) for the drop-down: the fixed priced list, or the fetched list."""
        if pid in LIVE_MODEL_PROVIDERS:
            return [(choice.model_id, _choice_label(choice)) for choice in self._choices.get(pid, ())]
        return [(model.model_id, model_label(model)) for model in models_for(pid)]

    def _fill_models(self) -> None:
        """Rebuild the model drop-down for the shown provider, selecting its saved model.

        A typed model name is kept while the provider stays the same, so a settings reload does not wipe it.
        """
        pid = self.current_provider()
        if pid != self._model_pid:
            self._model_pid = pid
            self._other_open = False
            self.model_name_box.setText("")
        selected = self._config.ai_model_for(pid)
        rows = self._model_rows(pid)
        if selected and selected not in {model_id for model_id, _ in rows}:
            rows.insert(0, (selected, selected))
        self.model_box.blockSignals(True)
        try:
            self.model_box.clear()
            for model_id, label in rows:
                self.model_box.addItem(label, model_id)
            self.model_box.addItem(OTHER_MODEL_TEXT, OTHER_MODEL_DATA)
            self.model_box.setCurrentIndex(self._model_index(selected))
        finally:
            self.model_box.blockSignals(False)
        self._other_open = self.model_box.currentData() is OTHER_MODEL_DATA
        self._show_typed_box(self._other_open)

    def _model_index(self, selected: str) -> int:
        if self._other_open:
            return self.model_box.count() - 1
        index = self.model_box.findData(selected) if selected else -1
        return index if index >= 0 else self.model_box.count() - 1

    def _show_typed_box(self, typed: bool) -> None:
        """The typed-name box, and the note on what a typed model costs (cloud providers only)."""
        pid = self.current_provider()
        self.model_name_box.setVisible(typed)
        live_prices = tuple(c.price for c in self._choices.get(pid, ()) if c.price is not None)
        note = estimated_price_text(provider(pid), live_prices) if typed else ""
        _set_note(self.estimated_label, note)

    def _on_model_picked(self) -> None:
        model = self.model_box.currentData()
        self._other_open = model is OTHER_MODEL_DATA
        self._show_typed_box(self._other_open)
        if not self._other_open:
            self._emit_model(model)

    def _on_model_typed(self) -> None:
        name = self.model_name_box.text().strip()
        if not is_valid_model_name(name):
            self._set_models_status(TYPED_MODEL_HINT)
            return
        self._set_models_status("")
        if name != self._config.ai_model_for(self.current_provider()):
            self._emit_model(name)

    def _emit_model(self, model: str) -> None:
        pid = self.current_provider()
        updated = self._config.with_ai_model(pid, model)
        if pid == DEFAULT_PROVIDER:
            self._emit(ai_model=updated.ai_model)
        else:
            self._emit(ai_models=updated.ai_models)

    def set_model_choices(self, pid: str, choices: tuple[ModelChoice, ...]) -> None:
        """A fetched model list for pid; shown when pid is the shown provider."""
        self._choices[pid] = tuple(choices)
        if pid == self.current_provider():
            self._fill_models()
            self._set_models_status("")

    def show_models_status(self, pid: str, text: str) -> None:
        if pid == self.current_provider():
            self._set_models_status(text)

    def _set_models_status(self, text: str) -> None:
        _set_note(self.model_status, text)

    def set_key_saved(self, pid: str, saved: bool) -> None:
        """Show the key box (no key) or "Key saved" with Remove (key saved); never the key itself.
        Ignored unless pid is the shown provider."""
        if pid != self.current_provider():
            return
        self._key_saved = saved
        if saved:
            self.key_box.clear()
        self.key_box.setVisible(not saved)
        self.save_button.setVisible(not saved)
        self.key_saved_label.setVisible(saved)
        self.remove_button.setVisible(saved)
        self.test_button.setEnabled(saved and not self._testing)

    @property
    def _testing(self) -> bool:
        return self._test_pid is not None

    def show_key_result(self, pid: str, ok: bool, message: str) -> None:
        """A key test's result; ignored unless pid is the shown provider. It ends the running test for pid,
        and when that test was for another provider, the shown provider's buttons are enabled again."""
        ended = pid == self._test_pid
        if ended:
            self._test_pid = None
        if pid != self.current_provider():
            if ended:
                self.test_button.setEnabled(self._key_saved)
                self._sync_address_test()
            return
        self.test_button.setEnabled(self._key_saved)
        self._sync_address_test()
        self._show_status(message, ok)

    def show_key_warning(self, pid: str, text: str) -> None:
        """A standing note under the key box, re-derived from the saved state on every refresh, so it survives a
        restart. Ignored for another provider, and while a Test runs (its "Testing..." line stays)."""
        if pid == self.current_provider() and not self._testing:
            self._show_status(text, ok=False)

    def _show_status(self, text: str, ok: bool) -> None:
        set_object_name(self.key_status, "statusOk" if ok else "statusError")
        self.key_status.setText(text)
        self.key_status.show()

    def _clear_key_status(self) -> None:
        self.key_status.setText("")
        self.key_status.hide()

    def clear_key_status(self) -> None:
        self._clear_key_status()

    def show_usage(self, text: str) -> None:
        self.usage_label.setText(text)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.shown.emit()

    def _on_test(self) -> None:
        self._test_pid = self.current_provider()
        self.test_button.setEnabled(False)
        self.address_test_button.setEnabled(False)
        set_object_name(self.key_status, "cardDescription")
        self.key_status.setText(TESTING_TEXT)
        self.key_status.show()
        self.key_test_requested.emit(self.current_provider())
