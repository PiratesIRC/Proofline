"""Settings window: Windows-11-style navigation rail, search, and setting cards.

Changes save as soon as they are made (see settings_pages); the server URL and
shortcuts apply with their own buttons. Errors show in a bar above the page.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from proofline.ai_settings_page import AiPage
from proofline.config import (
    Config,
    ConfigError,
    is_insecure_remote,
    normalize_server_url,
    redact_url,
)
from proofline.logging_setup import LOG_DIR
from proofline.settings_pages import (
    AdvancedPage,
    AppearancePage,
    AppsPage,
    CheckingPage,
    GeneralPage,
    Page,
    ShortcutsPage,
)
from proofline.ui_kit import InfoBar, apply_style

log = logging.getLogger(__name__)

WINDOW_TITLE = "Proofline – Settings"
DEFAULT_SIZE = (900, 640)
MIN_SIZE = (760, 520)
NAV_WIDTH = 230
CONTENT_MARGINS = (12, 4, 28, 20)

ConfigProvider = Callable[[], Config]
SaveHandler = Callable[[Config], Config]


class SettingsWindow(QWidget):
    pick_field_requested = pyqtSignal()  # "Add a text field…"
    update_check_requested = pyqtSignal()  # "Check now"

    def __init__(self, config_provider: ConfigProvider, save_handler: SaveHandler, log_dir: Path = LOG_DIR) -> None:
        super().__init__()
        self.setObjectName("uiRoot")
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MIN_SIZE)
        self._config_provider = config_provider
        self._save_handler = save_handler

        self.general = GeneralPage()
        self.checking = CheckingPage()
        self.apps = AppsPage()
        self.appearance = AppearancePage()
        self.shortcuts = ShortcutsPage()
        self.ai = AiPage()
        self.advanced = AdvancedPage(config_provider, log_dir)
        self.pages: tuple[Page, ...] = (
            self.general, self.checking, self.apps, self.appearance, self.shortcuts, self.ai, self.advanced,
        )
        for page in self.pages:
            page.changed.connect(self.apply_changes)
        self.general.server_save_requested.connect(self.save_server)
        self.apps.pick_field_requested.connect(self.pick_field_requested.emit)
        self.advanced.update_check_requested.connect(self.update_check_requested.emit)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a setting")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_settings)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.stack = QStackedWidget()
        for page in self.pages:
            self.nav.addItem(QListWidgetItem(page.title))
            self.stack.addWidget(_scrollable(page))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.error_bar = InfoBar("error")
        self.error_bar.hide()
        self._build_layout()

    def _build_layout(self) -> None:
        nav_column = QVBoxLayout()
        nav_column.setContentsMargins(12, 8, 8, 12)
        nav_column.addWidget(self.search)
        nav_column.addWidget(self.nav)
        nav_widget = QWidget()
        nav_widget.setFixedWidth(NAV_WIDTH)
        nav_widget.setLayout(nav_column)

        content = QVBoxLayout()
        content.setContentsMargins(*CONTENT_MARGINS)
        content.addWidget(self.error_bar)
        content.addWidget(self.stack)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(nav_widget)
        row.addLayout(content, stretch=1)

    def show_settings(self) -> None:
        self.reload()
        self.refresh_style()
        self.show()
        self.raise_()
        self.activateWindow()

    def reload(self) -> None:
        """Re-read every control from the current config (e.g. after a tray change)."""
        config = self._config_provider()
        for page in self.pages:
            page.load(config)

    def refresh_style(self) -> None:
        apply_style(self, self._config_provider().tray_color)

    def set_update_status(self, status: str) -> None:
        """Show the latest update check result (from the cache; never a network call)."""
        self.advanced.show_update_status(status)

    def config_changed(self) -> None:
        """Called by the app after any config change; keeps an open window in sync."""
        if self.isVisible():
            self.refresh_style()
            config = self._config_provider()
            for page in self.pages:
                if page is not self.general or self.general.url_text == config.server_url:
                    page.load(config)

    def apply_changes(self, changes: dict) -> bool:
        try:
            self._save_handler(replace(self._config_provider(), **changes))
        except ConfigError as exc:
            self._show_error(str(exc))
            return False
        except OSError as exc:
            log.exception("Failed to write config")
            self._show_error(f"Could not save settings: {exc}")
            return False
        self.error_bar.hide()
        return True

    def save_server(self, text: str) -> None:
        try:
            url = normalize_server_url(text)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        if url == self._config_provider().server_url:
            return
        if is_insecure_remote(url) and not self.confirm_insecure(url):
            return
        if self.apply_changes({"server_url": url}):
            self.general.load(self._config_provider())
            self.general.test_connection()  # so a user who skipped Test still sees whether it works

    def confirm_insecure(self, url: str) -> bool:
        answer = QMessageBox.warning(
            self, WINDOW_TITLE,
            f"{redact_url(url)} uses plain http:// to another computer.\n\n"
            "Everything you type will be sent over the network unencrypted. Save anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def filter_settings(self, query: str) -> None:
        """Hide cards that don't match and jump to the first page with a match."""
        query = query.strip()
        first_match = None
        for row, page in enumerate(self.pages):
            has_match = page.filter(query)
            self.nav.item(row).setHidden(bool(query) and not has_match)
            if has_match and first_match is None:
                first_match = row
        if query and first_match is not None:
            self.nav.setCurrentRow(first_match)

    def _show_error(self, message: str) -> None:
        self.error_bar.show_message("error", "Not saved.", message)
        self.error_bar.show()


def _scrollable(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area
