"""System tray icon and context menu.

The icon shows one state at a time, in this order: the server cannot be reached (red "!"),
checking is paused (grey), AI is on but its key or server fails (amber), otherwise the
chosen colour. A dot in the corner is added to any of them while a newer release waits.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from proofline import __version__
from proofline.app_icon import ICON_TEXT, make_icon
from proofline.app_identity import DISPLAY_NAME

ICON_SIZE = 64
ACTIVE_COLOR = "#2e7d32"
PAUSED_COLOR = "#757575"
ERROR_COLOR = "#b71c1c"
ERROR_GLYPH = "!"
AI_PROBLEM_COLOR = "#ffb300"
AI_PROBLEM_TEXT_COLOR = "#3e2723"
ERROR_TOOLTIP_TITLE = "Proofline: can't reach the server"
MAX_ERROR_MESSAGE_CHARS = 120
MAX_AI_MESSAGE_CHARS = 70  # Windows cuts a tray tooltip at 127 characters
TRAY_COLORS: dict[str, str] = {
    "Green": ACTIVE_COLOR,
    "Blue": "#1565c0",
    "Purple": "#6a1b9a",
    "Orange": "#ef6c00",
    "Teal": "#00838f",
    "Red": "#c62828",
}

# menu_action values
PAUSE_HOUR, PAUSE_TODAY = "pause_hour", "pause_today"
CHECK_FIELD, TOGGLE_APP = "check_field", "toggle_app"
OPEN_UPDATE, CHECK_UPDATES, WHATS_NEW = "open_update", "check_updates", "whats_new"
OPEN_LOGS, COPY_REPORT, RESTART = "open_logs", "copy_report", "restart"

UPDATE_MENU_TEXT = "Update available: {version}…"
UPDATE_TOOLTIP = "Update available: {version}"
TURN_OFF_APP_TEXT = "Turn off in {app}"
TURN_ON_APP_TEXT = "Turn on in {app}"
HELP_MENU_TITLE = "Help"
HELP_ITEMS = (
    ("Check for updates", CHECK_UPDATES),
    ("What's new", WHATS_NEW),
    ("Open log folder", OPEN_LOGS),
    ("Copy diagnostic report", COPY_REPORT),
)


def _error_tooltip(message: str) -> str:
    return f"{ERROR_TOOLTIP_TITLE}\n{message[:MAX_ERROR_MESSAGE_CHARS]}"


class TrayIcon(QSystemTrayIcon):
    settings_requested = pyqtSignal()
    pick_field_requested = pyqtSignal()
    flyout_requested = pyqtSignal()  # left-click: quick settings
    enabled_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()
    menu_action = pyqtSignal(str)  # one of the menu_action values above

    def __init__(self, enabled: bool, color: str = ACTIVE_COLOR) -> None:
        super().__init__()
        self._color = color
        self._error_message: str | None = None
        self._ai_problem: str | None = None
        self._update_version: str | None = None
        self._menu = self._build_menu()  # QSystemTrayIcon does not take ownership
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self._enabled_action.setChecked(enabled)
        self._refresh(enabled)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction(f"{DISPLAY_NAME} {__version__}").setEnabled(False)
        self._update_action = self._add(menu, "", OPEN_UPDATE)
        self._update_action.setVisible(False)
        menu.addSeparator()
        self._enabled_action = QAction("Checking enabled", menu, checkable=True)
        self._enabled_action.toggled.connect(self._on_enabled_toggled)
        menu.addAction(self._enabled_action)
        self._add(menu, "Pause for 1 hour", PAUSE_HOUR)
        self._add(menu, "Pause for the rest of today", PAUSE_TODAY)
        menu.addSeparator()
        self._add(menu, "Check the current field now", CHECK_FIELD)
        self._app_action = self._add(menu, "", TOGGLE_APP)
        self._app_action.setVisible(False)
        menu.addAction("Add a text field…", self.pick_field_requested.emit)
        menu.addSeparator()
        menu.addAction("Settings…", self.settings_requested.emit)
        help_menu = menu.addMenu(HELP_MENU_TITLE)
        for text, name in HELP_ITEMS:
            self._add(help_menu, text, name)
        menu.addSeparator()
        self._add(menu, f"Restart {DISPLAY_NAME}", RESTART)
        menu.addAction("Quit", self.quit_requested.emit)
        return menu

    def _add(self, menu: QMenu, text: str, name: str) -> QAction:
        action = QAction(text, menu)
        action.triggered.connect(lambda _checked=False: self.menu_action.emit(name))
        menu.addAction(action)
        return action

    @property
    def has_error(self) -> bool:
        return self._error_message is not None

    @property
    def update_version(self) -> str | None:
        return self._update_version

    @property
    def ai_problem(self) -> str | None:
        return self._ai_problem

    def set_color(self, color: str) -> None:
        """Recolour the active icon. The paused icon stays grey."""
        if not QColor(color).isValid():
            raise ValueError(f"Invalid tray icon colour: {color!r}")
        self._color = color
        self._refresh(self._enabled_action.isChecked())

    def set_error(self, message: str | None) -> None:
        """Show the error icon with the message, or clear it when message is None or empty."""
        self._error_message = message if message else None
        self._refresh(self._enabled_action.isChecked())

    def set_ai_problem(self, message: str | None) -> None:
        """Show the amber icon with the message while AI is on but cannot work; None clears it."""
        self._ai_problem = message if message else None
        self._refresh(self._enabled_action.isChecked())

    def set_update(self, version: str | None) -> None:
        """Mark the icon, tooltip and menu while a newer release waits; None clears the mark."""
        self._update_version = version if version else None
        self._update_action.setVisible(self._update_version is not None)
        self._update_action.setText(UPDATE_MENU_TEXT.format(version=self._update_version or ""))
        self._refresh(self._enabled_action.isChecked())

    def set_current_app(self, process: str, disabled: bool = False) -> None:
        """The app the user was last typing in, for the menu's "Turn off in <app>" item."""
        self._app_action.setVisible(bool(process))
        template = TURN_ON_APP_TEXT if disabled else TURN_OFF_APP_TEXT
        self._app_action.setText(template.format(app=process.replace("&", "&&")))

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
        self.setIcon(self._icon(enabled))
        lines = [self._state_line(enabled)]
        if self._error_message is None and enabled and self._ai_problem is not None:
            lines.append(f"AI: {self._ai_problem[:MAX_AI_MESSAGE_CHARS]}")
        if self._update_version is not None:
            lines.append(UPDATE_TOOLTIP.format(version=self._update_version))
        self.setToolTip("\n".join(lines))

    def _state_line(self, enabled: bool) -> str:
        if self._error_message is not None:
            return _error_tooltip(self._error_message)
        return f"Proofline ({'active' if enabled else 'paused'})"

    def _icon(self, enabled: bool) -> QIcon:
        dot = self._update_version is not None
        if self._error_message is not None:
            return make_icon(ERROR_COLOR, ERROR_GLYPH, dot)
        if not enabled:
            return make_icon(PAUSED_COLOR, ICON_TEXT, dot)
        if self._ai_problem is not None:
            return make_icon(AI_PROBLEM_COLOR, ICON_TEXT, dot, AI_PROBLEM_TEXT_COLOR)
        return make_icon(self._color, ICON_TEXT, dot)
