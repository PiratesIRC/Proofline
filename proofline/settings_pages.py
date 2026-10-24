"""The pages of the Settings window.

Each page loads its controls from a Config and emits `changed(dict)` with only the
fields the user just changed; the window saves them immediately. Loading never emits.
The server URL and shortcuts are the exceptions: they apply with an explicit button
so a half-typed value never takes effect.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from proofline import __version__
from proofline.config import (
    DEFAULT_DISABLED_APPS,
    DEFAULT_DISABLED_WINDOWS,
    DEFAULT_SERVER_URL,
    IS_PORTABLE,
    LANGUAGES,
    MIN_WORDS_RANGE,
    Config,
    ConfigError,
    is_insecure_remote,
    normalize_server_url,
    rule_label,
)
from proofline.diagnostics import build_report, clear_logs
from proofline.hotkeys import HotkeyError, parse_hotkey
from proofline.list_editor import StringListEditor
from proofline.server_test import ServerStatus, StatusLevel, run_server_test
from proofline.settings_widgets import (
    CATEGORIES_URL,
    CategoryChecklist,
    HotkeyRecorder,
    ServerStatusLabel,
    custom_field_label,
    rule_browser_url,
    running_app_button,
)
from proofline.tray import TRAY_COLORS
from proofline.ui_kit import (
    ExpanderCard,
    InfoBar,
    SettingCard,
    ToggleSwitch,
)
from proofline.update_check import RELEASES_PAGE_URL
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

URL_WIDTH = 260
COMBO_WIDTH = 190
SWATCH_PX = 14
DELAY_CHOICES_MS = (500, 1000, 1500, 2000, 3000, 5000)
THEME_CHOICES = (("Follow Windows", "auto"), ("Light", "light"), ("Dark", "dark"))
HOTKEY_FIELDS = (
    ("hotkey_toggle", "Pause or resume checking"),
    ("hotkey_check_now", "Check the current field now"),
    ("hotkey_fix_first", "Apply the first suggestion"),
)
HELP_URL = "https://github.com/PiratesIRC/Proofline/blob/main/docs/TROUBLESHOOTING.md"
CHANGELOG_URL = "https://github.com/PiratesIRC/Proofline/blob/main/CHANGELOG.md"
INSECURE_TITLE = "Unencrypted connection."
INSECURE_MESSAGE = (
    "This server uses http:// on another computer, so what you type travels over the "
    "network unencrypted. Use https:// if the server supports it."
)
RULES_LINK_TEXT = "Browse LanguageTool's rules (ids and what they check)"
CATEGORIES_LINK_TEXT = "List of LanguageTool categories"
SERVER_DESCRIPTION = "Where your text is checked"
LANGUAGETOOL_URL = "https://languagetool.org"
UPDATES_DESCRIPTION = "Asks GitHub once a day whether a newer Proofline release exists. Sends none of your text."
UPDATES_OFF_TEXT = "Update checks are off"
CHECKING_UPDATES_TEXT = "Checking for updates…"
SHARE_USAGE_DESCRIPTION = (
    "Sends the number of corrections you applied and a random id for this install to the author's "
    "counter at plugin-stats.dpas.workers.dev, at most once an hour, for the Active Installs and "
    "Corrections Applied badges. No text you type is sent. Turning this off deletes this install's "
    "figures from the server."
)
ATTRIBUTION_TEXT = (
    "Checking is done by the LanguageTool server you choose. Proofline is an independent "
    "project, not made by or affiliated with LanguageTooler GmbH."
)


class Page(QWidget):
    changed = pyqtSignal(dict)
    title = ""

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[QWidget] = []
        self._loading = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        heading = QLabel(self.title)
        heading.setObjectName("pageTitle")
        self._layout.addWidget(heading)

    def load(self, config: Config) -> None:
        self._loading = True
        try:
            self._load(config)
        finally:
            self._loading = False

    def filter(self, query: str) -> bool:
        """Show only cards matching query ('' shows all); True if any card matches."""
        any_match = False
        for card in self.cards:
            match = not query or card.matches(query)
            card.setVisible(match)
            any_match = any_match or match
        return any_match

    def _load(self, config: Config) -> None:
        raise NotImplementedError

    def _emit(self, **changes: object) -> None:
        if not self._loading:
            self.changed.emit(changes)

    def _group(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("groupTitle")
        self._layout.addWidget(label)

    def _card(self, card: QWidget) -> QWidget:
        self.cards.append(card)
        self._layout.addWidget(card)
        return card

    def _finish(self) -> None:
        self._layout.addStretch()


def _accent_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("accentButton")
    return button


def _switch(name: str, handler: Callable[[bool], None]) -> ToggleSwitch:
    switch = ToggleSwitch(name)
    switch.toggled.connect(handler)
    return switch


def _link_label(url: str, text: str) -> QLabel:
    """A plain link that opens in the default browser."""
    label = QLabel(f'<a href="{url}">{text}</a>')
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    return label


def _set_combo_data(combo: QComboBox, value: object, label: str) -> None:
    index = combo.findData(value)
    if index < 0:
        combo.addItem(label, value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


class GeneralPage(Page):
    title = "General"
    server_save_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._test_generation = 0
        self._url = QLineEdit()
        self._url.setPlaceholderText(DEFAULT_SERVER_URL)
        self._url.setMinimumWidth(URL_WIDTH)
        self._url.textChanged.connect(self._on_url_edited)
        self._test_button = QPushButton("Test")
        self._test_button.clicked.connect(self.test_connection)
        self._save_button = _accent_button("Save")
        self._save_button.clicked.connect(lambda: self.server_save_requested.emit(self._url.text()))
        self._language = QComboBox()
        self._language.setMinimumWidth(COMBO_WIDTH)
        for code, name in LANGUAGES.items():
            self._language.addItem(name, code)
        self._language.currentIndexChanged.connect(lambda: self._emit(language=self._language.currentData()))
        self._autostart = _switch("Start when I sign in to Windows", lambda on: self._emit(start_with_windows=on))
        self._saved_url = ""

        self._group("Server")
        self._server_card = self._card(
            SettingCard("LanguageTool server", SERVER_DESCRIPTION,
                        self._url, self._test_button, self._save_button, keywords="url connection http test")
        )
        self.status_label = ServerStatusLabel()
        self._layout.addWidget(self.status_label)
        self.insecure_bar = InfoBar("warning", INSECURE_TITLE, INSECURE_MESSAGE)
        self._layout.addWidget(self.insecure_bar)
        self._group("Language and startup")
        self._card(SettingCard("Language", "Auto-detect works for most text", self._language, keywords="english"))
        self._card(SettingCard("Start when I sign in to Windows", "", self._autostart, keywords="startup boot"))
        self._finish()

    def _load(self, config: Config) -> None:
        self._saved_url = config.server_url
        self._url.setText(config.server_url)
        _set_combo_data(self._language, config.language, config.language)
        self._autostart.setChecked(config.start_with_windows)

    @property
    def url_text(self) -> str:
        return self._url.text()

    def _on_url_edited(self, text: str) -> None:
        self._test_generation += 1  # any running test no longer matches the field
        self._test_button.setEnabled(True)
        try:
            insecure = is_insecure_remote(normalize_server_url(text))
        except ConfigError:
            insecure = False
        self.insecure_bar.setVisible(insecure)
        self._save_button.setEnabled(text.strip() != self._saved_url)
        self.status_label.hide()  # the last result was for another address

    def test_connection(self) -> None:
        """Check the test sentence against the address in the box; the result shows in status_label."""
        self._test_generation += 1
        generation = self._test_generation
        url_text, language = self._url.text(), self._language.currentData()
        self._test_button.setEnabled(False)
        self.status_label.show_testing()
        run_in_background(
            lambda: run_server_test(url_text, language),
            lambda result: self._on_test_done(generation, result),
            lambda exc: self._on_test_done(generation, ServerStatus(StatusLevel.UNREACHABLE, "Test failed", str(exc))),
        )

    def _on_test_done(self, generation: int, result: ServerStatus) -> None:
        if generation != self._test_generation:
            log.debug("Discarding stale connection-test result")
            return
        self._test_button.setEnabled(True)
        self.show_test_result(result)

    def show_test_result(self, result: ServerStatus) -> None:
        self.status_label.show_result(result)


class CheckingPage(Page):
    title = "Checking"

    def __init__(self) -> None:
        super().__init__()
        self._delay = QComboBox()
        self._delay.setMinimumWidth(COMBO_WIDTH)
        for ms in DELAY_CHOICES_MS:
            self._delay.addItem(_seconds(ms), ms)
        self._delay.currentIndexChanged.connect(lambda: self._emit(debounce_ms=self._delay.currentData()))
        self._min_words = QSpinBox()
        self._min_words.setRange(*MIN_WORDS_RANGE)
        self._min_words.valueChanged.connect(self._sync_words_suffix)
        self._min_words.valueChanged.connect(lambda value: self._emit(min_words=value))
        self._picky = _switch("Picky mode", lambda on: self._emit(picky=on))
        self._words = StringListEditor("", "e.g. Dispatcharr")
        self._words.items_changed.connect(lambda: self._emit(personal_dictionary=self._words.items()))
        self._rules = StringListEditor("Turned-off rules", "Rule id, e.g. WHITESPACE_RULE")
        self._rules.items_changed.connect(lambda: self._emit(disabled_rules=self._rules.items()))
        self._categories = CategoryChecklist()
        self._categories.changed.connect(lambda: self._emit(disabled_categories=self._categories.disabled()))

        self._group("When to check")
        self._card(SettingCard("Check after I stop typing for", "", self._delay, keywords="delay pause debounce"))
        self._card(SettingCard("Only check text with at least", "Ctrl+Alt+L checks any text right away",
                               self._min_words, keywords="minimum words length"))
        self._group("Suggestions")
        self._card(SettingCard("Picky mode", "Also suggest style and punctuation improvements",
                               self._picky, keywords="strict style"))
        self._dictionary = self._card(ExpanderCard("Personal dictionary", "Words never flagged as misspelled",
                                                   keywords="spelling words ignore"))
        self._dictionary.body_layout.addWidget(self._words)
        self._rules_card = self._card(ExpanderCard("Turned-off rules and categories",
                                                   "Rules can also be turned off from the issues popup",
                                                   keywords="rules categories disable"))
        self.rules_link = _link_label(rule_browser_url("auto"), RULES_LINK_TEXT)
        self.categories_link = _link_label(CATEGORIES_URL, CATEGORIES_LINK_TEXT)
        for widget in (self._rules, self.rules_link, QLabel("Turned-off categories"), self._categories,
                       self.categories_link):
            self._rules_card.body_layout.addWidget(widget)
        self._finish()

    def _load(self, config: Config) -> None:
        _set_combo_data(self._delay, config.debounce_ms, _seconds(config.debounce_ms))
        self._min_words.setValue(config.min_words)
        self._picky.setChecked(config.picky)
        self._words.set_items(config.personal_dictionary)
        self._rules.set_label(lambda rule_id: rule_label(config, rule_id))
        self.rules_link.setText(f'<a href="{rule_browser_url(config.language)}">{RULES_LINK_TEXT}</a>')
        self._rules.set_items(config.disabled_rules)
        self._categories.set_disabled(config.disabled_categories)
        self._dictionary.set_summary(_count(len(config.personal_dictionary), "word"))
        self._rules_card.set_summary(
            f"{_count(len(config.disabled_rules), 'rule')} · {_count(len(config.disabled_categories), 'category')}"
        )


    def _sync_words_suffix(self, value: int) -> None:
        self._min_words.setSuffix(" word" if value == 1 else " words")


class AppsPage(Page):
    title = "Apps & fields"
    pick_field_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        pick = _accent_button("Add a text field…")
        pick.clicked.connect(self.pick_field_requested.emit)
        self._card(SettingCard("Add a text field", "Click any text box to see why it is or isn’t checked, and turn it on",
                               pick, keywords="picker custom diagnose"))
        self._group("Don’t check in")
        self._lists: dict[str, tuple[ExpanderCard, StringListEditor, str]] = {}
        apps = self._list_card("disabled_apps", "Apps", "Password managers, terminals, remote desktops and code editors",
                               "e.g. KeePass.exe", "app", "exclude exclusions")
        recommended = QPushButton("Add recommended exclusions")
        recommended.clicked.connect(self._add_recommended)
        apps.body_layout.addWidget(running_app_button(self._lists["disabled_apps"][1].add_item))
        apps.body_layout.addWidget(recommended)
        self._list_card("disabled_windows", "Window titles containing", "Sign-in, password and remote desktop windows",
                        "e.g. Remote Desktop", "title", "exclude exclusions login")
        self._group("Always check")
        always = self._list_card("always_check_apps", "Apps", "Checked even if an exclusion matches", "e.g. erp.exe",
                                 "app", "always include")
        always.body_layout.addWidget(running_app_button(self._lists["always_check_apps"][1].add_item))
        self._list_card("custom_fields", "Custom text fields", "Added with “Add a text field…”",
                        "Advanced: app.exe|ControlType|ClassName", "field", "custom signature",
                        label=custom_field_label)
        self._finish()

    def _list_card(self, field: str, title: str, description: str, placeholder: str, noun: str,
                   keywords: str, label: Callable[[str], str] | None = None) -> ExpanderCard:
        card = self._card(ExpanderCard(title, description, keywords=keywords))
        editor = StringListEditor("", placeholder, label=label)
        editor.items_changed.connect(lambda: self._emit(**{field: editor.items()}))
        card.body_layout.addWidget(editor)
        self._lists[field] = (card, editor, noun)
        return card

    def _load(self, config: Config) -> None:
        for field, (card, editor, noun) in self._lists.items():
            values = getattr(config, field)
            editor.set_items(values)
            card.set_summary(_count(len(values), noun))

    def _add_recommended(self) -> None:
        _card, apps, _noun = self._lists["disabled_apps"]
        _card, windows, _noun = self._lists["disabled_windows"]
        for editor, defaults in ((apps, DEFAULT_DISABLED_APPS), (windows, DEFAULT_DISABLED_WINDOWS)):
            for value in defaults:
                editor.add_item(value)


class AppearancePage(Page):
    title = "Appearance"

    def __init__(self) -> None:
        super().__init__()
        self._theme = QComboBox()
        self._theme.setMinimumWidth(COMBO_WIDTH)
        for label, value in THEME_CHOICES:
            self._theme.addItem(label, value)
        self._theme.currentIndexChanged.connect(lambda: self._emit(theme=self._theme.currentData()))
        self._tray_color = QComboBox()
        self._tray_color.setMinimumWidth(COMBO_WIDTH)
        for name, color in TRAY_COLORS.items():
            self._tray_color.addItem(_swatch(color), name, color)
        self._tray_color.currentIndexChanged.connect(lambda: self._emit(tray_color=self._tray_color.currentData()))
        self._badge = _switch("Show the badge in every text field", lambda on: self._emit(badge_always_visible=on))

        self._card(SettingCard("Theme", "Light, dark, or the same as Windows", self._theme, keywords="dark light mode"))
        self._card(SettingCard("Accent and tray icon colour", "", self._tray_color, keywords="color colour tray"))
        self._card(SettingCard("Show the badge in every text field", "When off, it appears only when there are issues",
                               self._badge, keywords="badge icon"))
        self._finish()

    def _load(self, config: Config) -> None:
        _set_combo_data(self._theme, config.theme, config.theme)
        _set_combo_data(self._tray_color, config.tray_color, f"Custom ({config.tray_color})")
        self._badge.setChecked(config.badge_always_visible)


class ShortcutsPage(Page):
    title = "Shortcuts"

    def __init__(self) -> None:
        super().__init__()
        self._edits: dict[str, HotkeyRecorder] = {}
        for field, label in HOTKEY_FIELDS:
            edit = HotkeyRecorder()
            edit.setMinimumWidth(COMBO_WIDTH)
            self._edits[field] = edit
            self._card(SettingCard(label, "", edit, keywords="hotkey keyboard"))
        self.error_bar = InfoBar("error")
        self.error_bar.hide()
        self._layout.addWidget(self.error_bar)
        apply_button = _accent_button("Apply")
        apply_button.clicked.connect(self.apply_shortcuts)
        self._card(SettingCard("Apply shortcuts", "Click a box and press the keys, e.g. CTRL+ALT+P. Backspace clears "
                               "a box, which turns that shortcut off.",
                               apply_button, keywords="hotkey"))
        self._finish()

    def _load(self, config: Config) -> None:
        for field, edit in self._edits.items():
            edit.set_hotkey(getattr(config, field))
        self.error_bar.hide()

    def apply_shortcuts(self) -> None:
        try:
            values = validate_hotkeys({field: edit.hotkey() for field, edit in self._edits.items()})
        except ConfigError as exc:
            self.error_bar.show_message("error", "Shortcut not applied.", str(exc))
            self.error_bar.show()
            return
        self.error_bar.hide()
        self._emit(**values)


def validate_hotkeys(values: dict[str, str]) -> dict[str, str]:
    """Normalise and validate hotkey strings; raises ConfigError with a friendly message."""
    cleaned = {field: value.strip().lower() for field, value in values.items()}
    labels = dict(HOTKEY_FIELDS)
    for field, value in cleaned.items():
        if not value:
            continue
        try:
            parse_hotkey(value)
        except HotkeyError as exc:
            raise ConfigError(f"{labels.get(field, field)}: {exc}") from exc
    used = [v for v in cleaned.values() if v]
    if len(used) != len(set(used)):
        raise ConfigError("Each shortcut must be different.")
    return cleaned


class AdvancedPage(Page):
    title = "Advanced"
    update_check_requested = pyqtSignal()

    def __init__(self, config_provider: Callable[[], Config], log_dir: Path) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._log_dir = log_dir
        self._debug = _switch("Debug mode", lambda on: self._emit(debug_mode=on))
        self.result_bar = InfoBar("success")
        self.result_bar.hide()
        buttons = {
            "Copy diagnostic report": self.copy_report,
            "Open log folder": self.open_log_folder,
            "Clear logs": self.clear_logs,
        }
        self._card(SettingCard("Debug mode", "Adds short samples of what you type to the log. Turn it off and clear the "
                               "logs when you are done.", self._debug, keywords="log diagnostics"))
        diagnostics = self._card(SettingCard("Diagnostics", "For reporting a problem", keywords="report log support"))
        for label, handler in buttons.items():
            button = QPushButton(label)
            button.clicked.connect(handler)
            diagnostics.add_control(button)
        self._layout.addWidget(self.result_bar)
        self._updates = _switch("Check for updates", lambda on: self._emit(check_for_updates=on))
        self.check_now_button = QPushButton("Check now")
        self.check_now_button.clicked.connect(self._on_check_now)
        self._card(SettingCard("Check for updates", UPDATES_DESCRIPTION, self.check_now_button, self._updates,
                               keywords="update version release github"))
        self._share_usage = _switch("Share anonymous usage counts", lambda on: self._emit(share_usage_counts=on))
        self._card(SettingCard("Share anonymous usage counts", SHARE_USAGE_DESCRIPTION, self._share_usage,
                               keywords="usage statistics telemetry privacy badge"))
        self._storage_text = f"Settings and logs are stored in {log_dir.parent}"
        self.help_link = _link_label(HELP_URL, "Help")
        self.changelog_link = _link_label(CHANGELOG_URL, "What's new")
        self.about_card = self._card(SettingCard("About", "", self.help_link, self.changelog_link,
                                                 _link_label(RELEASES_PAGE_URL, "Releases"),
                                                 keywords="version folder update help troubleshooting changelog"))
        self.show_update_status("")
        self.attribution_link = _link_label(LANGUAGETOOL_URL, "languagetool.org")
        self._card(SettingCard("Powered by LanguageTool", ATTRIBUTION_TEXT, self.attribution_link,
                               keywords="about credits attribution affiliated"))
        self._finish()

    def _load(self, config: Config) -> None:
        self._debug.setChecked(config.debug_mode)
        self._updates.setChecked(config.check_for_updates)
        self._share_usage.setChecked(config.share_usage_counts)
        self.result_bar.hide()

    def _on_check_now(self) -> None:
        self.show_update_status(CHECKING_UPDATES_TEXT)
        self.update_check_requested.emit()

    def show_update_status(self, status: str) -> None:
        """status: the update check's one-line result ('' while none is known yet)."""
        edition = " (portable)" if IS_PORTABLE else ""
        version = f"Proofline {__version__}{edition}" + (f". {status}" if status else "")
        self.about_card.set_description(f"{version}\n{self._storage_text}")

    def copy_report(self) -> None:
        QGuiApplication.clipboard().setText(build_report(self._config_provider(), self._log_dir))
        self._result("success", "Report copied. Paste it into your issue report.")

    def open_log_folder(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_dir))):
            self._result("error", f"Could not open {self._log_dir}")

    def clear_logs(self) -> None:
        if not self.confirm_clear_logs():
            return
        try:
            cleared = clear_logs(self._log_dir)
        except OSError as exc:
            log.exception("Failed to clear logs")
            self._result("error", f"Could not clear logs: {exc}")
            return
        self._result("success", f"Cleared {cleared} log file(s).")

    def confirm_clear_logs(self) -> bool:
        answer = QMessageBox.question(
            self, "Clear logs", "Delete all log files? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _result(self, severity: str, message: str) -> None:
        self.result_bar.show_message(severity, "", message)
        self.result_bar.show()


def _seconds(ms: int) -> str:
    seconds = ms / 1000
    return f"{seconds:g} second" + ("" if seconds == 1 else "s")


def _count(n: int, noun: str) -> str:
    plural = "categories" if noun == "category" else f"{noun}s"
    return f"{n} {noun if n == 1 else plural}"


def _swatch(color: str) -> QIcon:
    pixmap = QPixmap(SWATCH_PX, SWATCH_PX)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)
