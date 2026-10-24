"""Small widget for editing a list of strings (used for the exclusion lists)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

LIST_MIN_HEIGHT = 60
LIST_PREFERRED_HEIGHT = 100  # about five rows; the list still grows with the window


class _CompactList(QListWidget):
    """QListWidget asks for ~190 px by default, which makes multi-list tabs very tall."""

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), LIST_PREFERRED_HEIGHT)


class StringListEditor(QWidget):
    """A titled list with an input box, Add, and Remove. Duplicates (ignoring case) are skipped.

    items_changed fires when the user adds or removes entries (not on set_items). label, if
    given, turns a stored value into the text shown; items() always returns the values.
    """

    items_changed = pyqtSignal()

    def __init__(self, title: str, placeholder: str, label: Callable[[str], str] | None = None) -> None:
        super().__init__()
        self._label = label or (lambda value: value)
        self._list = _CompactList()
        self._list.setMinimumHeight(LIST_MIN_HEIGHT)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.returnPressed.connect(self._add_from_input)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_from_input)
        self._remove_button = QPushButton("Remove")
        self._remove_button.clicked.connect(self._remove_selected)
        self._remove_button.setEnabled(False)
        self._list.itemSelectionChanged.connect(
            lambda: self._remove_button.setEnabled(bool(self._list.selectedItems()))
        )

        row = QHBoxLayout()
        row.addWidget(self._input, stretch=1)
        row.addWidget(add_button)
        row.addWidget(self._remove_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if title:
            layout.addWidget(QLabel(title))
        layout.addWidget(self._list)
        layout.addLayout(row)

    def items(self) -> tuple[str, ...]:
        return tuple(self._list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self._list.count()))

    def set_items(self, items: tuple[str, ...]) -> None:
        self._list.clear()
        for value in items:
            self._append(value)

    def set_label(self, label: Callable[[str], str]) -> None:
        """Change how values are shown (e.g. when the names they map to changed)."""
        self._label = label
        self.set_items(self.items())

    def _append(self, value: str) -> None:
        item = QListWidgetItem(self._label(value))
        item.setData(Qt.ItemDataRole.UserRole, value)
        item.setToolTip(value)
        self._list.addItem(item)

    def add_item(self, text: str) -> bool:
        """Add a stripped, non-empty, not-yet-listed entry. Returns whether it was added."""
        entry = text.strip()
        if not entry or entry.casefold() in {item.casefold() for item in self.items()}:
            return False
        self._append(entry)
        self.items_changed.emit()
        return True

    def _add_from_input(self) -> None:
        if self.add_item(self._input.text()):
            self._input.clear()
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _remove_selected(self) -> None:
        selected = self._list.selectedItems()
        for item in selected:
            self._list.takeItem(self._list.row(item))
        if selected:
            self.items_changed.emit()
