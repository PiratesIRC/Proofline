"""Applies settings that live outside the app's own windows: theme, tray colour,
Start with Windows, and global shortcuts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import ModuleType

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from proofline import autostart as autostart_module
from proofline.autostart import AutostartError
from proofline.config import Config
from proofline.hotkeys import HotkeyError, HotkeyManager
from proofline.theme import apply_theme
from proofline.tray import TrayIcon

log = logging.getLogger(__name__)

# Hotkey action name -> Config field holding its key combination.
HOTKEY_ACTIONS = {
    "toggle": "hotkey_toggle",
    "check_now": "hotkey_check_now",
    "fix_first": "hotkey_fix_first",
    "ai_rephrase": "hotkey_ai_rephrase",
}


class DesktopIntegration(QObject):
    hotkey_triggered = pyqtSignal(str)  # action name from HOTKEY_ACTIONS

    def __init__(
        self,
        qt_app: QGuiApplication,
        tray: TrayIcon,
        notify: Callable[[str], None],
        hotkeys: HotkeyManager | None = None,
        autostart: ModuleType = autostart_module,
    ) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._tray = tray
        self._notify = notify
        self._hotkeys = hotkeys or HotkeyManager()
        self._autostart = autostart
        self._hotkeys.triggered.connect(self.hotkey_triggered.emit)

    def apply(self, config: Config, previous: Config | None = None) -> None:
        """Apply everything on startup (previous=None), otherwise only what changed."""
        if previous is None or config.theme != previous.theme:
            apply_theme(self._qt_app, config.theme)
        if previous is None or config.tray_color != previous.tray_color:
            self._tray.set_color(config.tray_color)
        if previous is None or _hotkeys(config) != _hotkeys(previous):
            self._register_hotkeys(config)
        if previous is None or config.start_with_windows != previous.start_with_windows:
            self._sync_autostart(config.start_with_windows)

    def preview_appearance(self, config: Config) -> None:
        """Apply theme and tray colour immediately while the user is choosing them."""
        apply_theme(self._qt_app, config.theme)
        self._tray.set_color(config.tray_color)

    def shutdown(self) -> None:
        self._hotkeys.unregister_all()

    def _register_hotkeys(self, config: Config) -> None:
        self._hotkeys.unregister_all()
        for action, field_name in HOTKEY_ACTIONS.items():
            combo = getattr(config, field_name)
            if not combo:
                continue
            try:
                self._hotkeys.register(action, combo)
                log.info("Shortcut %s -> %s", combo, action)
            except HotkeyError as exc:
                log.warning("Could not register shortcut %s: %s", combo, exc)
                self._notify(f"Shortcut {combo} could not be set: {exc}")

    def _sync_autostart(self, enabled: bool) -> None:
        """Match the Run value to the setting. An entry pointing somewhere else (say, the
        source checkout after switching to the packaged exe) is rewritten."""
        try:
            if enabled:
                if self._autostart.stored_command() != self._autostart.launch_command():
                    self._autostart.set_enabled(True)
            elif self._autostart.is_enabled():
                self._autostart.set_enabled(False)
        except AutostartError as exc:
            log.warning("Start with Windows could not be changed: %s", exc)
            self._notify(str(exc))


def _hotkeys(config: Config) -> tuple[str, ...]:
    return tuple(getattr(config, field_name) for field_name in HOTKEY_ACTIONS.values())
