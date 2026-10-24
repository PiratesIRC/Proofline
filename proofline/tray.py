"""System tray icon and context menu."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

ICON_SIZE = 64
ICON_FONT_PX = 34
ICON_TEXT = "P"
ACTIVE_COLOR = "#2e7d32"
PAUSED_COLOR = "#757575"
ERROR_COLOR = "#b71c1c"
ERROR_GLYPH = "!"
ERROR_TOOLTIP_TITLE = "Proofline: can't reach the server"
MAX_ERROR_MESSAGE_CHARS = 120
TRAY_COLORS: dict[str, str] = {
    "Green": ACTIVE_COLOR,
    "Blue": "#1565c0",
    "Purple": "#6a1b9a",
    "Orange": "#ef6c00",
    "Teal": "#00838f",
    "Red": "#c62828",
}


def make_icon(color: str, text: str = ICON_TEXT) -> QIcon:
    """Draw a round badge with white text so the app needs no image assets."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, ICON_SIZE - 4, ICON_SIZE - 4)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(ICON_FONT_PX)  # pixels, so it fits regardless of screen DPI
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, ICON_SIZE, ICON_SIZE), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


def _error_tooltip(message: str) -> str:
    return f"{ERROR_TOOLTIP_TITLE}\n{message[:MAX_ERROR_MESSAGE_CHARS]}"


class TrayIcon(QSystemTrayIcon):
    settings_requested = pyqtSignal()
    pick_field_requested = pyqtSignal()
    flyout_requested = pyqtSignal()  # left-click: quick settings
    enabled_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()

    def __init__(self, enabled: bool, color: str = ACTIVE_COLOR) -> None:
        super().__init__()
        self._active_icon = make_icon(color)
        self._paused_icon = make_icon(PAUSED_COLOR)
        self._error_icon = make_icon(ERROR_COLOR, ERROR_GLYPH)
        self._error_message: str | None = None

        menu = QMenu()
        self._enabled_action = QAction("Checking enabled", menu, checkable=True)
        self._enabled_action.toggled.connect(self._on_enabled_toggled)
        menu.addAction(self._enabled_action)
        menu.addSeparator()
        menu.addAction("Add a text field…", self.pick_field_requested.emit)
        menu.addAction("Settings…", self.settings_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_requested.emit)
        self._menu = menu  # QSystemTrayIcon does not take ownership
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)
        self._enabled_action.setChecked(enabled)
        self._refresh(enabled)

    @property
    def has_error(self) -> bool:
        return self._error_message is not None

    def set_color(self, color: str) -> None:
        """Recolour the active icon. The paused icon stays grey."""
        if not QColor(color).isValid():
            raise ValueError(f"Invalid tray icon colour: {color!r}")
        self._active_icon = make_icon(color)
        self._refresh(self._enabled_action.isChecked())

    def set_error(self, message: str | None) -> None:
        """Show the error icon with the message, or clear it when message is None or empty."""
        self._error_message = message if message else None
        self._refresh(self._enabled_action.isChecked())

    @property
    def is_enabled(self) -> bool:
        return self._enabled_action.isChecked()

    def set_enabled(self, enabled: bool) -> None:
        """Set checking on/off as if the menu item were clicked (emits enabled_toggled on change)."""
        self._enabled_action.setChecked(enabled)

    def toggle_enabled(self) -> None:
        """Flip checking on/off as if the menu item were clicked."""
        self._enabled_action.toggle()

    def _on_enabled_toggled(self, enabled: bool) -> None:
        self._refresh(enabled)
        self.enabled_toggled.emit(enabled)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.flyout_requested.emit()

    def _refresh(self, enabled: bool) -> None:
        if self._error_message is not None:
            self.setIcon(self._error_icon)
            self.setToolTip(_error_tooltip(self._error_message))
            return
        self.setIcon(self._active_icon if enabled else self._paused_icon)
        state = "active" if enabled else "paused"
        self.setToolTip(f"Proofline ({state})")
