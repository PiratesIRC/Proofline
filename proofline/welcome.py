"""First-run welcome: connect to a server, see how the badge works, choose Start with Windows.

Shown once, on a fresh install only (no settings file existed at startup). Closing it
at any point counts as seen; only Finish saves the server and startup choices.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from PyQt6.QtCore import QPoint, QProcess, Qt
from PyQt6.QtGui import QCloseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from proofline.badge import BadgeState, BadgeWidget
from proofline.config import (
    DEFAULT_SERVER_URL,
    Config,
    ConfigError,
    is_insecure_remote,
    normalize_server_url,
    redact_url,
)
from proofline.server_test import ServerStatus, StatusLevel, run_server_test
from proofline.settings_widgets import ServerStatusLabel
from proofline.ui_kit import InfoBar, ToggleSwitch, apply_style
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

WINDOW_TITLE = "Welcome to Proofline"
WINDOW_SIZE = (580, 470)
PAGE_COUNT = 3
BADGE_SCALE = 1.6
BADGE_RENDER_SCALE = 3  # drawn at 3x and shown at BADGE_SCALE, so it stays sharp on any display
WELCOME_STYLE = "QWidget#uiRoot QLabel#welcomeHeading { font-size: 20px; font-weight: 600; }"
NOTEPAD = "notepad.exe"
SERVER_INTRO = (
    "Proofline sends the text you type to a LanguageTool server and shows the fixes it suggests. "
    "Use a server you run yourself, so your text stays on your network."
)
THIS_PC_TEXT = "This PC (a LanguageTool server on port 8010)"
OTHER_TEXT = "Another server:"
HOW_INTRO = "Click into a text box in almost any app. A small badge appears at its corner:"
HOW_OUTRO = (
    "Click the red badge to see the suggestions, then click one to fix the text. "
    "Proofline never checks its own windows, so try it in another app."
)
BADGE_CAPTIONS = ((BadgeState.CHECKING, 0, "Checking"), (BadgeState.CLEAN, 0, "No issues"),
                  (BadgeState.ISSUES, 3, "3 issues"), (BadgeState.ERROR, 0, "Server problem"))
DONE_TEXT = (
    "Proofline runs in the system tray: look for the round P icon (it may be inside the ^ overflow "
    "area). Left-click it for quick settings, right-click it for the menu. Everything here can be "
    "changed later in Settings."
)
INSECURE_TITLE = "Unencrypted connection."
INSECURE_MESSAGE = (
    "This server uses http:// on another computer, so what you type travels over the network "
    "unencrypted. Use https:// if the server supports it."
)
PAGE_TITLES = ("Connect to your LanguageTool server", "How it works", "You are all set")


def should_show_welcome(config: Config, config_existed: bool) -> bool:
    """Fresh installs only: people upgrading already have a settings file."""
    return not config_existed and not config.welcome_shown


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("welcomeHeading")
    return label


def _paragraph(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class WelcomeWindow(QWidget):
    def __init__(self, config_provider: Callable[[], Config], save: Callable[[Config], object]) -> None:
        super().__init__()
        self.setObjectName("uiRoot")
        self.setWindowTitle(WINDOW_TITLE)
        self.setFixedSize(*WINDOW_SIZE)
        self._config_provider = config_provider
        self._save = save
        self._finished = False
        self._test_generation = 0
        self._pages = QStackedWidget()
        for build in (self._server_page, self._how_page, self._done_page):
            self._pages.addWidget(build())
        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("accentButton")
        self.back_button.clicked.connect(lambda: self._go(self.page_index() - 1))
        self.next_button.clicked.connect(self._on_next)
        self.step_label = QLabel()
        self.step_label.setObjectName("cardDescription")
        buttons = QHBoxLayout()
        buttons.addWidget(self.step_label)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.addWidget(self._pages, stretch=1)
        layout.addLayout(buttons)
        apply_style(self, config_provider().tray_color, lambda _tokens: WELCOME_STYLE)
        self._go(0)

    # ----- pages ------------------------------------------------------------

    def _server_page(self) -> QWidget:
        page = QWidget()
        self.this_pc = QRadioButton(THIS_PC_TEXT)
        self.other_server = QRadioButton(OTHER_TEXT)
        group = QButtonGroup(page)
        group.addButton(self.this_pc)
        group.addButton(self.other_server)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://languagetool.example.org")
        current = self._config_provider().server_url
        is_default = current == DEFAULT_SERVER_URL
        (self.this_pc if is_default else self.other_server).setChecked(True)
        self.url_edit.setText("" if is_default else current)
        self.other_server.toggled.connect(self._sync_url_enabled)
        self.url_edit.textEdited.connect(lambda: self.status.hide())
        self.url_edit.textChanged.connect(self._sync_insecure)
        self.insecure_bar = InfoBar("warning", INSECURE_TITLE, INSECURE_MESSAGE)
        self.insecure_bar.hide()
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self.test_connection)
        self.status = ServerStatusLabel()
        other_row = QHBoxLayout()
        other_row.addWidget(self.other_server)
        other_row.addWidget(self.url_edit, stretch=1)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.status, stretch=1)
        layout = QVBoxLayout(page)
        layout.addWidget(_heading(PAGE_TITLES[0]))
        layout.addWidget(_paragraph(SERVER_INTRO))
        layout.addSpacing(8)
        layout.addWidget(self.this_pc)
        layout.addLayout(other_row)
        layout.addWidget(self.insecure_bar)
        layout.addSpacing(8)
        layout.addLayout(test_row)
        layout.addStretch(1)
        self._sync_url_enabled()
        return page

    def _how_page(self) -> QWidget:
        page = QWidget()
        badges = QHBoxLayout()
        for state, count, caption in BADGE_CAPTIONS:
            badges.addLayout(self._badge_sample(state, count, caption))
        try_button = QPushButton("Try it in Notepad")
        try_button.clicked.connect(lambda: QProcess.startDetached(NOTEPAD, []))
        layout = QVBoxLayout(page)
        layout.addWidget(_heading(PAGE_TITLES[1]))
        layout.addWidget(_paragraph(HOW_INTRO))
        layout.addLayout(badges)
        layout.addWidget(_paragraph(HOW_OUTRO))
        layout.addWidget(try_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _badge_sample(self, state: BadgeState, count: int, caption: str) -> QVBoxLayout:
        badge = BadgeWidget(animations_enabled=lambda: False)  # painted into a pixmap, never shown
        badge.set_state(state, count)
        pixmap = QPixmap(badge.size() * BADGE_RENDER_SCALE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.scale(BADGE_RENDER_SCALE, BADGE_RENDER_SCALE)
        badge.render(painter, QPoint(0, 0))
        painter.end()
        badge.deleteLater()
        pixmap.setDevicePixelRatio(BADGE_RENDER_SCALE / BADGE_SCALE)
        image = QLabel()
        image.setPixmap(pixmap)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(caption)
        text.setObjectName("cardDescription")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column = QVBoxLayout()
        column.addWidget(image)
        column.addWidget(text)
        return column

    def _done_page(self) -> QWidget:
        page = QWidget()
        self.autostart = ToggleSwitch("Start Proofline when I sign in to Windows")
        self.autostart.setChecked(self._config_provider().start_with_windows)
        row = QHBoxLayout()
        row.addWidget(QLabel("Start Proofline when I sign in to Windows"), stretch=1)
        row.addWidget(self.autostart)
        layout = QVBoxLayout(page)
        layout.addWidget(_heading(PAGE_TITLES[2]))
        layout.addWidget(_paragraph(DONE_TEXT))
        layout.addSpacing(12)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    # ----- behaviour --------------------------------------------------------

    def page_index(self) -> int:
        return self._pages.currentIndex()

    def server_url(self) -> str:
        return self.url_edit.text().strip() if self.other_server.isChecked() else DEFAULT_SERVER_URL

    def test_connection(self) -> None:
        self._test_generation += 1
        generation, url = self._test_generation, self.server_url()
        language = self._config_provider().language
        self.test_button.setEnabled(False)
        self.status.show_testing()
        run_in_background(
            lambda: run_server_test(url, language),
            lambda result: self._on_tested(generation, result),
            lambda exc: self._on_tested(generation, ServerStatus(StatusLevel.UNREACHABLE, "Test failed", str(exc))),
        )

    def _on_tested(self, generation: int, result: ServerStatus) -> None:
        if generation == self._test_generation:
            self.test_button.setEnabled(True)
            self.status.show_result(result)

    def _sync_url_enabled(self) -> None:
        self.url_edit.setEnabled(self.other_server.isChecked())
        self.status.hide()
        self._sync_insecure()

    def _sync_insecure(self) -> None:
        if hasattr(self, "insecure_bar"):  # textChanged can fire while the page is being built
            self.insecure_bar.setVisible(self._insecure_url() is not None)

    def _insecure_url(self) -> str | None:
        """The normalised address when it is plain http:// to another computer, else None."""
        try:
            url = normalize_server_url(self.server_url())
        except ConfigError:
            return None
        return url if is_insecure_remote(url) else None

    def confirm_insecure(self, url: str) -> bool:
        """The same question Settings asks before saving such an address."""
        answer = QMessageBox.warning(
            self, WINDOW_TITLE,
            f"{redact_url(url)} uses plain http:// to another computer.\n\n"
            "Everything you type will be sent over the network unencrypted. Use it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _go(self, index: int) -> None:
        index = max(0, min(index, PAGE_COUNT - 1))
        self._pages.setCurrentIndex(index)
        self.back_button.setEnabled(index > 0)
        self.next_button.setText("Finish" if index == PAGE_COUNT - 1 else "Next")
        self.step_label.setText(f"Step {index + 1} of {PAGE_COUNT}")

    def _on_next(self) -> None:
        index = self.page_index()
        if index == 0 and not self._address_ok():
            return
        if index < PAGE_COUNT - 1:
            self._go(index + 1)
        else:
            self._finish()

    def _address_ok(self) -> bool:
        try:
            normalize_server_url(self.server_url())
        except ConfigError as exc:
            self.status.show_result(ServerStatus(StatusLevel.UNREACHABLE, "Address not valid", str(exc)))
            return False
        insecure = self._insecure_url()
        return insecure is None or self.confirm_insecure(insecure)

    def _finish(self) -> None:
        config = replace(self._config_provider(), server_url=normalize_server_url(self.server_url()),
                         start_with_windows=self.autostart.isChecked(), welcome_shown=True)
        self._store(config)
        self._finished = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._finished:
            self._store(replace(self._config_provider(), welcome_shown=True))
            self._finished = True
        super().closeEvent(event)

    def _store(self, config: Config) -> None:
        try:
            self._save(config)
        except (OSError, ConfigError):
            log.exception("Could not save the welcome choices")
