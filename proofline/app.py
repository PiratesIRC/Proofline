"""Wires the tray, settings window, and checker components together."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from proofline.app_identity import DISPLAY_NAME
from proofline.checker import GrammarChecker
from proofline.config import CONFIG_PATH, Config, load_config, save_config
from proofline.field_picker import FieldPickerDialog
from proofline.health import OutageNotices, ServerHealth
from proofline.integration import DesktopIntegration
from proofline.logging_setup import set_debug_mode
from proofline.overlay_controller import OverlayController
from proofline.quick_settings import QuickSettings, connected_message
from proofline.settings_window import SettingsWindow
from proofline.setup_hints import SetupHint, unseen
from proofline.text_monitor import TextMonitor
from proofline.tray import TrayIcon

log = logging.getLogger(__name__)

APP_NAME = DISPLAY_NAME
NOTIFICATION_MS = 5000
HINT_NOTIFICATION_MS = 15000


class LanguageToolApp(QObject):
    def __init__(
        self,
        qt_app: QApplication,
        config_path: Path = CONFIG_PATH,
        monitor: TextMonitor | None = None,
        overlay: OverlayController | None = None,
        integration: DesktopIntegration | None = None,
        health: ServerHealth | None = None,
        quick: QuickSettings | None = None,
    ) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._config_path = config_path
        self._config = load_config(config_path)
        self._outage_notices = OutageNotices()
        log.info("Loaded config: %r", self._config)
        set_debug_mode(self._config.debug_mode)

        self._settings = SettingsWindow(lambda: self._config, self._save)

        self._tray = TrayIcon(self._config.enabled, self._config.tray_color)
        self._tray.settings_requested.connect(self._settings.show_settings)
        self._tray.enabled_toggled.connect(self._on_enabled_toggled)
        self._tray.quit_requested.connect(self._quit)

        self._checker = GrammarChecker(lambda: self._config)
        self._health = health or ServerHealth(lambda: self._config)
        self._health.healthy.connect(self._on_server_healthy)
        self._health.unhealthy.connect(self._on_server_unhealthy)
        self._checker.checked.connect(lambda *_: self._health.report_success())
        self._checker.failed.connect(self._health.report_failure)

        self._monitor = monitor or TextMonitor(self._config)
        self._monitor.text_ready.connect(self._checker.check)
        self._monitor.replace_finished.connect(self._on_replace_finished)
        self._monitor.hint_available.connect(self._on_setup_hint)

        self._overlay = overlay or OverlayController(lambda: self._config)
        self._monitor.field_changed.connect(self._overlay.on_field_changed)
        self._checker.checked.connect(self._overlay.on_checked)
        self._checker.failed.connect(self._overlay.on_check_failed)
        self._overlay.replace_requested.connect(self._monitor.request_replace)
        self._overlay.disable_app_requested.connect(self._disable_app)
        self._overlay.disable_window_requested.connect(self._disable_window)
        self._overlay.settings_requested.connect(self._settings.show_settings)
        self._overlay.add_word_requested.connect(self._add_word)
        self._overlay.disable_rule_requested.connect(self._disable_rule)
        self._overlay.undo_requested.connect(self._undo)

        self._picker = FieldPickerDialog(lambda: self._config)
        self._picker.capture_started.connect(self._monitor.start_capture)
        self._picker.capture_stopped.connect(self._monitor.stop_capture)
        self._monitor.captured.connect(self._picker.on_captured)
        self._picker.add_field_requested.connect(self._add_custom_field)
        self._picker.add_app_requested.connect(self._always_check_app)
        self._tray.pick_field_requested.connect(self._picker.open_picker)
        self._settings.pick_field_requested.connect(self._picker.open_picker)

        self._quick = quick or QuickSettings(lambda: self._config, self._save_quietly, self._tray)
        self._quick.settings_requested.connect(self._settings.show_settings)
        self._quick.pick_field_requested.connect(self._picker.open_picker)
        self._quick.quit_requested.connect(self._quit)
        self._monitor.focus_changed.connect(self._quick.on_focus_changed)

        self._integration = integration or DesktopIntegration(qt_app, self._tray, self._notify)
        self._integration.hotkey_triggered.connect(self._on_hotkey)

    @property
    def config(self) -> Config:
        return self._config

    def start(self) -> None:
        self._integration.apply(self._config)
        self._tray.show()
        self._quick.restore_pause()
        self._health.check_now()
        self._monitor.start()
        log.info("%s started", APP_NAME)

    def _save(self, config: Config) -> Config:
        saved = save_config(config, self._config_path)
        self._set_config(saved)
        log.info("Config updated: %r", saved)
        return saved

    def _set_config(self, config: Config) -> None:
        previous, self._config = self._config, config
        set_debug_mode(config.debug_mode)
        self._monitor.set_config(config)
        self._integration.apply(config, previous)
        self._overlay.on_config_changed()
        self._settings.config_changed()
        self._quick.refresh()
        if (config.server_url, config.language) != (previous.server_url, previous.language):
            self._health.check_now()

    def _on_hotkey(self, action: str) -> None:
        log.info("Shortcut pressed: %s", action)
        if action == "toggle":
            self._tray.toggle_enabled()
        elif action == "check_now":
            self._monitor.request_check_now()

    def _on_enabled_toggled(self, enabled: bool) -> None:
        log.info("Checking %s", "enabled" if enabled else "paused")
        self._quick.on_enabled_changed(enabled)
        try:
            self._save(replace(self._config, enabled=enabled))
        except OSError:
            log.exception("Could not persist enabled state")
            self._set_config(replace(self._config, enabled=enabled))

    def _on_server_healthy(self) -> None:
        self._tray.set_error(None)
        self._outage_notices.recovered()
        self._quick.on_server_status(True, connected_message(self._config.server_url))

    def _on_server_unhealthy(self, message: str) -> None:
        self._tray.set_error(message)
        self._quick.on_server_status(False, message)
        self._on_check_failed(message)

    def _disable_app(self, process_name: str) -> None:
        log.info("Disabling checking in %s", process_name)
        self._save_quietly(
            replace(self._config, disabled_apps=(*self._config.disabled_apps, process_name))
        )

    def _disable_window(self, window_title: str) -> None:
        log.info("Disabling checking in window %r", window_title)
        self._save_quietly(
            replace(self._config, disabled_windows=(*self._config.disabled_windows, window_title))
        )

    def _add_word(self, word: str) -> None:
        log.info("Adding a word to the personal dictionary")
        self._save_quietly(
            replace(self._config, personal_dictionary=(*self._config.personal_dictionary, word))
        )

    def _disable_rule(self, rule_id: str) -> None:
        log.info("Turning off rule %s", rule_id)
        self._save_quietly(
            replace(self._config, disabled_rules=(*self._config.disabled_rules, rule_id))
        )

    def _undo(self, field: str, value: str) -> None:
        """Undo a popup action: remove value from the config list it was added to."""
        log.info("Undoing a change to %s", field)
        values = list(getattr(self._config, field))
        if value in values:
            del values[len(values) - 1 - values[::-1].index(value)]  # the most recent addition
        self._save_quietly(replace(self._config, **{field: tuple(values)}))

    def _on_setup_hint(self, hint: SetupHint) -> None:
        if unseen(hint, self._config.shown_hints) is None:
            return
        log.info("Showing setup tip %s", hint.key)
        self._tray.showMessage(
            hint.title, hint.message, QSystemTrayIcon.MessageIcon.Information, HINT_NOTIFICATION_MS
        )
        self._save_quietly(replace(self._config, shown_hints=(*self._config.shown_hints, hint.key)))

    def _add_custom_field(self, signature: str) -> None:
        log.info("Always checking custom field %s", signature)
        self._save_quietly(replace(self._config, custom_fields=(*self._config.custom_fields, signature)))

    def _always_check_app(self, process_name: str) -> None:
        log.info("Always checking app %s", process_name)
        name = process_name.casefold()
        self._save_quietly(
            replace(
                self._config,
                always_check_apps=(*self._config.always_check_apps, process_name),
                disabled_apps=tuple(a for a in self._config.disabled_apps if a.casefold() != name),
            )
        )

    def _save_quietly(self, config: Config) -> None:
        """Apply a change made from the overlay; still apply it in memory if saving fails."""
        try:
            self._save(config)
        except OSError as exc:
            log.exception("Could not save settings")
            self._set_config(config)
            self._notify(f"Could not save settings: {exc}")

    def _on_replace_finished(self, ok: bool, message: str) -> None:
        if not ok:
            self._notify(message)

    def _notify(self, message: str) -> None:
        self._tray.showMessage(
            APP_NAME, message, QSystemTrayIcon.MessageIcon.Warning, NOTIFICATION_MS
        )

    def _on_check_failed(self, message: str) -> None:
        if self._outage_notices.should_notify():
            self._notify(message)

    def _quit(self) -> None:
        log.info("Quit requested")
        self._monitor.stop()
        self._integration.shutdown()
        self._tray.hide()
        self._qt_app.quit()
