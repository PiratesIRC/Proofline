"""Connects the tray quick-settings flyout to the app: which app the user is in, the
timed pause, server status, and the flyout's toggles."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from proofline.config import Config
from proofline.text_snapshot import FocusResult
from proofline.tray import TrayIcon
from proofline.tray_flyout import FlyoutState, TrayFlyout

log = logging.getLogger(__name__)

PAUSE = timedelta(hours=1)
MS_PER_S = 1000
IGNORED_REASONS = frozenset({"", "focus is in this app", "checking paused", "no focused element"})
STATUS_CHECKED = "Being checked"
STATUS_OFF = "Turned off here"
STATUS_NO_FIELD = "No text box focused"


def connected_message(server_url: str) -> str:
    return f"Connected to {urlparse(server_url).hostname or server_url}"


def pause_label(until: datetime) -> str:
    return until.strftime("%I:%M %p").lstrip("0")


class QuickSettings(QObject):
    settings_requested = pyqtSignal()
    pick_field_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(
        self,
        config_provider: Callable[[], Config],
        save: Callable[[Config], None],
        tray: TrayIcon,
        flyout: TrayFlyout | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._save = save
        self._tray = tray
        self._clock = clock
        self.flyout = flyout or TrayFlyout()
        self._paused_until: datetime | None = None
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self.resume)
        self._app: tuple[str, str, str] | None = None  # process, window title, status
        self._server_ok: bool | None = None
        self._server_message = ""
        self._connect_flyout()
        tray.flyout_requested.connect(self.show)

    def _connect_flyout(self) -> None:
        f = self.flyout
        f.enabled_toggled.connect(self._tray.set_enabled)
        f.picky_toggled.connect(lambda on: self._update(picky=on))
        f.pause_requested.connect(self.pause)
        f.resume_requested.connect(self.resume)
        f.language_chosen.connect(lambda code: self._update(language=code))
        f.disable_app_requested.connect(self._disable_app)
        f.enable_app_requested.connect(self._enable_app)
        f.pick_field_requested.connect(self.pick_field_requested.emit)
        f.settings_requested.connect(self.settings_requested.emit)
        f.quit_requested.connect(self.quit_requested.emit)

    @property
    def paused_until(self) -> datetime | None:
        return self._paused_until

    def state(self) -> FlyoutState:
        config = self._config_provider()
        process, title, status = self._app or ("", "", "")
        disabled = bool(process) and config.is_disabled_for(process, title)
        return FlyoutState(
            enabled=config.enabled,
            picky=config.picky,
            language=config.language,
            paused_until=pause_label(self._paused_until) if self._paused_until else "",
            server_ok=self._server_ok,
            server_message=self._server_message,
            current_app=process,
            current_app_status=STATUS_OFF if disabled else status,
            current_app_disabled=disabled,
            accent=config.tray_color,
        )

    def show(self) -> None:
        self.flyout.set_state(self.state())
        icon_rect = self._tray.geometry()
        screen = QGuiApplication.screenAt(icon_rect.center()) or QGuiApplication.primaryScreen()
        self.flyout.show_at(icon_rect, screen.availableGeometry())

    def refresh(self) -> None:
        if self.flyout.isVisible():
            self.flyout.set_state(self.state())

    def on_focus_changed(self, result: FocusResult) -> None:
        if not result.process_name or result.reason in IGNORED_REASONS:
            return
        if result.snapshot is not None:
            status = STATUS_CHECKED
        elif result.reason.startswith("disabled for"):
            status = STATUS_OFF
        else:
            status = STATUS_NO_FIELD
        self._app = (result.process_name, result.window_title, status)
        self.refresh()

    def on_server_status(self, ok: bool, message: str) -> None:
        self._server_ok = ok
        self._server_message = message
        self.refresh()

    def on_enabled_changed(self, enabled: bool) -> None:
        if enabled and self._paused_until is not None:
            self._cancel_pause()
        self.refresh()

    def pause(self) -> None:
        until = self._clock() + PAUSE
        self._start_pause(until)
        log.info("Checking paused until %s", pause_label(until))
        self._tray.set_enabled(False)
        # Saved so the pause still ends on time if the app restarts in between.
        self._update(paused_until=until.isoformat(timespec="seconds"))

    def resume(self) -> None:
        self._cancel_pause()
        self._tray.set_enabled(True)
        self.refresh()

    def restore_pause(self) -> None:
        """Pick up a timed pause saved before the app last quit; resume if it has ended."""
        config = self._config_provider()
        if not config.paused_until:
            return
        until = datetime.fromisoformat(config.paused_until)
        if config.enabled:
            self._update(paused_until="")  # checking was turned back on some other way
        elif until > self._clock():
            self._start_pause(until)
            log.info("Restored pause until %s", pause_label(until))
        else:
            log.info("Saved pause has ended; resuming checking")
            self.resume()

    def _start_pause(self, until: datetime) -> None:
        self._paused_until = until
        remaining = max(until - self._clock(), timedelta(0))
        self._pause_timer.start(int(remaining.total_seconds() * MS_PER_S))

    def _cancel_pause(self) -> None:
        self._pause_timer.stop()
        self._paused_until = None
        if self._config_provider().paused_until:
            self._update(paused_until="")

    def _update(self, **changes: object) -> None:
        self._save(replace(self._config_provider(), **changes))
        self.refresh()

    def _disable_app(self, process: str) -> None:
        config = self._config_provider()
        self._update(disabled_apps=(*config.disabled_apps, process))

    def _enable_app(self, process: str) -> None:
        """Remove the app's exclusion; if a window-title rule still matches, always check the app."""
        config = self._config_provider()
        name = process.casefold()
        apps = tuple(a for a in config.disabled_apps if a.casefold() != name)
        _, title, _ = self._app or ("", "", "")
        still_off = replace(config, disabled_apps=apps).is_disabled_for(process, title)
        always = (*config.always_check_apps, process) if still_off else config.always_check_apps
        self._update(disabled_apps=apps, always_check_apps=always)
