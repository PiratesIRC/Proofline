"""Settings controls that show readable names instead of raw values.

- CategoryChecklist: LanguageTool rule categories as named checkboxes.
- HotkeyRecorder: press the keys instead of typing "ctrl+alt+p".
- running_app_menu: pick an app with an open window instead of typing its exe name.
- custom_field_label: "app.exe|ControlType|ClassName" as a short sentence.
- ServerStatusLabel: the green / orange / red result of a connection test.
"""

from __future__ import annotations

import html
from collections.abc import Callable

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFocusEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QWidget,
)

from proofline.app_names import running_apps
from proofline.hotkeys import display_hotkey, hotkey_from_key
from proofline.server_test import ServerStatus, StatusLevel
from proofline.ui_kit import set_object_name

# Common LanguageTool categories (ids from Categories.java) with the names people know them by.
CATEGORY_NAMES: dict[str, str] = {
    "TYPOS": "Spelling",
    "GRAMMAR": "Grammar",
    "PUNCTUATION": "Punctuation",
    "CASING": "Capital letters",
    "CONFUSED_WORDS": "Commonly confused words",
    "STYLE": "Style",
    "REDUNDANCY": "Redundant phrases",
    "REPETITIONS": "Repeated words",
    "TYPOGRAPHY": "Typography (quotes, dashes, spaces)",
    "SEMANTICS": "Possible meaning problems",
}
RULE_BROWSER_URL = "https://community.languagetool.org/rule/list?lang={language}"
CATEGORIES_URL = (
    "https://github.com/languagetool-org/languagetool/blob/master/"
    "languagetool-core/src/main/java/org/languagetool/rules/Categories.java"
)


def rule_browser_url(language: str) -> str:
    """LanguageTool's rule browser for the chosen language (English when auto-detecting)."""
    return RULE_BROWSER_URL.format(language="en" if not language or language == "auto" else language)
CHECKLIST_COLUMNS = 2
RECORDER_PROMPT = "Press the keys"
CLEAR_KEYS = frozenset({Qt.Key.Key_Backspace, Qt.Key.Key_Delete})
FIELD_SEPARATOR = "|"
NO_APPS_TEXT = "No other app has an open window"
TESTING_TEXT = "Testing…"
# Per test level: label object name (colour) and a shape, so colour isn't the only cue.
STATUS_STYLE = {
    StatusLevel.READY: ("statusOk", "●"),
    StatusLevel.PROBLEM: ("statusWarn", "▲"),
    StatusLevel.UNREACHABLE: ("statusError", "✕"),
}


class ServerStatusLabel(QLabel):
    """One line: "● Ready", "▲ Language not available …" or "✕ Can't connect …". Hidden until used."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("cardDescription")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.hide()

    def show_testing(self) -> None:
        self._set("cardDescription", TESTING_TEXT)

    def show_result(self, result: ServerStatus) -> None:
        object_name, glyph = STATUS_STYLE[result.level]
        detail = f"&nbsp;&nbsp;{html.escape(result.detail, quote=False)}" if result.detail else ""
        self._set(object_name, f"<b>{glyph} {html.escape(result.title, quote=False)}</b>{detail}")

    def _set(self, object_name: str, text: str) -> None:
        set_object_name(self, object_name)
        self.setText(text)
        self.show()


class CategoryChecklist(QWidget):
    """Ticked boxes are turned-off categories. Unknown ones from the config stay listed."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._boxes: dict[str, QCheckBox] = {}
        for category in CATEGORY_NAMES:
            self._add_box(category)

    def box(self, category: str) -> QCheckBox:
        return self._boxes[category]

    def set_disabled(self, categories: tuple[str, ...]) -> None:
        """Load without emitting."""
        for category in categories:
            if category not in self._boxes:
                self._add_box(category)
        for category, box in self._boxes.items():
            box.blockSignals(True)
            box.setChecked(category in categories)
            box.blockSignals(False)

    def disabled(self) -> tuple[str, ...]:
        return tuple(category for category, box in self._boxes.items() if box.isChecked())

    def _add_box(self, category: str) -> None:
        box = QCheckBox(CATEGORY_NAMES.get(category, category))
        box.setToolTip(category)
        box.toggled.connect(lambda _on: self.changed.emit())
        index = len(self._boxes)
        self._grid.addWidget(box, index // CHECKLIST_COLUMNS, index % CHECKLIST_COLUMNS)
        self._boxes[category] = box


class HotkeyRecorder(QLineEdit):
    """Records the next key combination pressed while focused. Backspace or Delete clears it."""

    def __init__(self) -> None:
        super().__init__()
        self._hotkey = ""
        self.setReadOnly(True)
        self.setPlaceholderText(RECORDER_PROMPT)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def hotkey(self) -> str:
        """The combination in config form, e.g. "ctrl+alt+p"; "" when off."""
        return self._hotkey

    def set_hotkey(self, value: str) -> None:
        self._hotkey = value.strip().lower()
        self.setText(display_hotkey(self._hotkey))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = Qt.Key(event.key())
        if key in CLEAR_KEYS and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.set_hotkey("")
            return
        combination = hotkey_from_key(key, event.modifiers())
        if combination:
            self.set_hotkey(combination)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.setPlaceholderText(RECORDER_PROMPT)


def custom_field_label(signature: str) -> str:
    parts = signature.split(FIELD_SEPARATOR)
    if len(parts) != 3:
        return signature
    app, control_type, class_name = parts
    return f"{app}: {control_type}" + (f" ({class_name})" if class_name else "")


def running_app_button(add: Callable[[str], object], apps: Callable[[], list[tuple[str, str]]] = running_apps) -> QPushButton:
    """A button that lists apps with open windows by name and adds the chosen exe."""
    button = QPushButton("Pick a running app…")

    def show_menu() -> None:
        menu = running_app_menu(button, add, apps())
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))

    button.clicked.connect(show_menu)
    return button


def running_app_menu(parent: QWidget, add: Callable[[str], object], apps: list[tuple[str, str]]) -> QMenu:
    menu = QMenu(parent)
    if not apps:
        menu.addAction(NO_APPS_TEXT).setEnabled(False)
    for exe, name in apps:
        action = QAction(name if name == exe else f"{name} ({exe})", menu)
        action.triggered.connect(lambda _checked=False, value=exe: add(value))
        menu.addAction(action)
    return menu
