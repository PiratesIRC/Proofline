"""Tray quick-settings flyout: the panel shown when the user left-clicks the tray icon.

A frameless popup in the style of the Windows 11 quick settings panel. set_state() syncs
every widget without emitting signals. User clicks emit the matching signal, and one-shot
actions hide the flyout afterwards. Call show_at() to restyle (theme may have changed).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from proofline.config import DEFAULT_TRAY_COLOR, LANGUAGES
from proofline.ui_kit import (
    DARK,
    apply_style,
    current_tokens,
    link_button,
    readable_accent,
    set_object_name,
)
from proofline.window_corners import round_corners

log = logging.getLogger(__name__)

FLYOUT_WIDTH = 360
CARD_PADDING = 16
CARD_SPACING = 12
GRID_SPACING = 8
TILE_MIN_HEIGHT = 64
BADGE_SIZE = 36
GEAR_SIZE = 32
EDGE_MARGIN = 12
BADGE_TEXT = "P"
APP_TITLE = "Proofline"
CHECKING_TILE_TITLE = "Checking"
PICKY_TILE_TITLE = "Picky mode"
PAUSE_TILE_TITLE = "Pause for 1 hour"
PAUSE_TILE_HINT = "Ctrl+Alt+P to toggle"
PAUSED_TILE_TITLE = "Paused"
RESUME_HINT = "click to resume"
LANGUAGE_TILE_TITLE = "Language"
ON_LABEL = "On"
OFF_LABEL = "Off"
CHECKING_STATUS = "Checking connection…"
OK_GLYPH = "●"
WARNING_GLYPH = "⚠"
CURRENT_APP_CAPTION = "Current app"
NO_APP_TEXT = "No app yet — click into a text box"
DISABLE_APP_TEXT = "Turn off in this app"
ENABLE_APP_TEXT = "Turn back on"
ADD_FIELD_TEXT = "Add a text field…"
MORE_SETTINGS_TEXT = "More settings"
QUIT_TEXT = "Quit"
SETTINGS_GLYPH = "⚙"
SETTINGS_NAME = "Settings"


@dataclass(frozen=True)
class FlyoutState:
    enabled: bool
    picky: bool
    language: str
    paused_until: str = ""
    server_ok: bool | None = None
    server_message: str = ""
    current_app: str = ""
    current_app_status: str = ""
    current_app_disabled: bool = False
    accent: str = DEFAULT_TRAY_COLOR


INITIAL_STATE = FlyoutState(enabled=True, picky=False, language="auto")


def flyout_position(
    icon_rect: QRect, size: QSize, available: QRect, margin: int = EDGE_MARGIN
) -> QPoint:
    """Place a flyout of `size` beside the tray icon, kept inside `available`.

    A taskbar at the bottom or top puts the flyout above or below it, right edge lined up
    with the icon. A taskbar on the left or right puts it beside the taskbar, bottom edge
    lined up with the icon. A null icon rect uses the bottom-right corner of `available`.
    """
    if icon_rect.isNull() or icon_rect.isEmpty():
        x_anchor = available.right() - margin - size.width() + 1
        y_anchor = available.bottom() - margin - size.height() + 1
    elif _is_side_taskbar(icon_rect, available):
        x_anchor, y_anchor = _side_anchor(icon_rect, size, available, margin)
    else:
        x_anchor = icon_rect.right() - size.width() + 1
        if icon_rect.center().y() >= available.center().y():
            y_anchor = available.bottom() - margin - size.height() + 1
        else:
            y_anchor = available.top() + margin
    x = _fit(x_anchor, size.width(), available.left(), available.right(), margin)
    y = _fit(y_anchor, size.height(), available.top(), available.bottom(), margin)
    return QPoint(x, y)


def _is_side_taskbar(icon_rect: QRect, available: QRect) -> bool:
    """The icon sits left or right of the work area, so the taskbar is vertical."""
    x = icon_rect.center().x()
    return x < available.left() or x > available.right()


def _side_anchor(icon_rect: QRect, size: QSize, available: QRect, margin: int) -> tuple[int, int]:
    if icon_rect.center().x() < available.left():
        x = available.left() + margin
    else:
        x = available.right() - margin - size.width() + 1
    return x, icon_rect.bottom() - size.height() + 1


def _fit(anchor: int, extent: int, low: int, high: int, margin: int) -> int:
    """Clamp a span of `extent` px starting at `anchor` into [low, high].

    Keeps `margin` px from the edges when there is room for it.
    """
    start_min = low + margin
    start_max = high - margin - extent + 1
    if start_max < start_min:
        start_min, start_max = low, high - extent + 1
    return max(start_min, min(anchor, start_max))


def _tile_text(title: str, subtitle: str) -> str:
    return f"{title}\n{subtitle}"


def _language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def _set_checked_silently(button: QPushButton, checked: bool) -> None:
    button.blockSignals(True)
    button.setChecked(checked)
    button.blockSignals(False)


def _bold(label: QLabel) -> QLabel:
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class TrayFlyout(QWidget):
    enabled_toggled = pyqtSignal(bool)
    picky_toggled = pyqtSignal(bool)
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    language_chosen = pyqtSignal(str)
    disable_app_requested = pyqtSignal(str)
    enable_app_requested = pyqtSignal(str)
    pick_field_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = INITIAL_STATE
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # Opaque on purpose: Windows 11 only rounds (and shadows) non-layered windows.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(FLYOUT_WIDTH)
        round_corners(self)
        self._build_ui()
        self.set_state(INITIAL_STATE)
        self._restyle(INITIAL_STATE.accent)

    # ----- public API -------------------------------------------------------

    def set_state(self, state: FlyoutState) -> None:
        """Sync every widget to `state`. Emits no signals."""
        self._state = state
        self._sync_toggles(state)
        self._sync_pause_tile(state.paused_until)
        self._sync_language(state.language)
        self._sync_header(state)
        self._sync_app_card(state)

    def show_at(self, icon_rect: QRect, available: QRect) -> None:
        """Show the flyout next to the tray icon, restyled for the current theme."""
        self._restyle(self._state.accent)
        self.adjustSize()
        self.move(flyout_position(icon_rect, self.size(), available))
        self.show()
        self.raise_()
        self.activateWindow()
        log.debug("Tray flyout shown at %s", self.pos())

    # ----- construction -----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(self)
        panel.setObjectName("flyoutPanel")
        root.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        layout.setSpacing(CARD_SPACING)
        layout.addLayout(self._build_header())
        layout.addLayout(self._build_tiles())
        layout.addWidget(self._build_app_card())
        layout.addLayout(self._build_footer())
        self._language_menu = self._build_language_menu()

    def _build_header(self) -> QHBoxLayout:
        self._badge = QLabel(BADGE_TEXT)
        self._badge.setFixedSize(BADGE_SIZE, BADGE_SIZE)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(_bold(QLabel(APP_TITLE)))
        text.addWidget(self._status_label)
        self._gear_button = link_button(SETTINGS_GLYPH)
        self._gear_button.setAccessibleName(SETTINGS_NAME)
        self._gear_button.setToolTip(SETTINGS_NAME)
        self._gear_button.setFixedSize(GEAR_SIZE, GEAR_SIZE)
        self._gear_button.clicked.connect(self._on_settings_clicked)
        row = QHBoxLayout()
        row.setSpacing(CARD_SPACING)
        row.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(text, stretch=1)
        row.addWidget(self._gear_button, alignment=Qt.AlignmentFlag.AlignTop)
        return row

    def _build_tiles(self) -> QGridLayout:
        self._enabled_tile = self._make_tile(checkable=True)
        self._picky_tile = self._make_tile(checkable=True)
        self._pause_tile = self._make_tile(checkable=False)
        self._language_tile = self._make_tile(checkable=False)
        self._enabled_tile.clicked.connect(self._on_enabled_clicked)
        self._picky_tile.clicked.connect(self._on_picky_clicked)
        self._pause_tile.clicked.connect(self._on_pause_clicked)
        self._language_tile.clicked.connect(self._on_language_tile_clicked)
        grid = QGridLayout()
        grid.setSpacing(GRID_SPACING)
        grid.addWidget(self._enabled_tile, 0, 0)
        grid.addWidget(self._picky_tile, 0, 1)
        grid.addWidget(self._pause_tile, 1, 0)
        grid.addWidget(self._language_tile, 1, 1)
        return grid

    def _make_tile(self, checkable: bool) -> QPushButton:
        tile = QPushButton(self)
        tile.setObjectName("tile")
        tile.setCheckable(checkable)
        tile.setMinimumHeight(TILE_MIN_HEIGHT)
        # Equal columns regardless of text length.
        tile.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        return tile

    def _build_app_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(4)
        caption = QLabel(CURRENT_APP_CAPTION)
        caption.setObjectName("cardDescription")
        self._app_name = _bold(QLabel())
        self._app_status = QLabel()
        self._app_status.setObjectName("cardDescription")
        self._app_status.setWordWrap(True)
        self._disable_app_button = QPushButton(DISABLE_APP_TEXT)
        self._enable_app_button = QPushButton(ENABLE_APP_TEXT)
        self._add_field_button = QPushButton(ADD_FIELD_TEXT)
        self._disable_app_button.clicked.connect(self._on_disable_app_clicked)
        self._enable_app_button.clicked.connect(self._on_enable_app_clicked)
        self._add_field_button.clicked.connect(self._on_add_field_clicked)
        app_row = QHBoxLayout()
        app_row.addWidget(self._disable_app_button)
        app_row.addWidget(self._enable_app_button)
        app_row.addStretch(1)
        layout.addWidget(caption)
        layout.addWidget(self._app_name)
        layout.addWidget(self._app_status)
        layout.addLayout(app_row)
        layout.addWidget(self._add_field_button, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_footer(self) -> QHBoxLayout:
        more_settings = link_button(MORE_SETTINGS_TEXT)
        more_settings.clicked.connect(self._on_settings_clicked)
        quit_button = QPushButton(QUIT_TEXT)
        quit_button.clicked.connect(self._on_quit_clicked)
        row = QHBoxLayout()
        row.addWidget(more_settings)
        row.addStretch(1)
        row.addWidget(quit_button)
        return row

    def _build_language_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for code, name in LANGUAGES.items():
            action = QAction(name, menu)
            action.setCheckable(True)
            action.setData(code)
            group.addAction(action)
            menu.addAction(action)
        menu.triggered.connect(self._on_language_action)
        return menu

    # ----- syncing widgets to state (never emits) ---------------------------

    def _sync_toggles(self, state: FlyoutState) -> None:
        _set_checked_silently(self._enabled_tile, state.enabled)
        self._enabled_tile.setText(
            _tile_text(CHECKING_TILE_TITLE, ON_LABEL if state.enabled else OFF_LABEL)
        )
        _set_checked_silently(self._picky_tile, state.picky)
        self._picky_tile.setText(
            _tile_text(PICKY_TILE_TITLE, ON_LABEL if state.picky else OFF_LABEL)
        )

    def _sync_pause_tile(self, paused_until: str) -> None:
        if paused_until:
            # Tiles cannot word-wrap, so the resume hint goes on its own line.
            text = f"{PAUSED_TILE_TITLE}\nUntil {paused_until}\n{RESUME_HINT}"
        else:
            text = _tile_text(PAUSE_TILE_TITLE, PAUSE_TILE_HINT)
        self._pause_tile.setText(text)

    def _sync_language(self, code: str) -> None:
        self._language_tile.setText(_tile_text(LANGUAGE_TILE_TITLE, _language_name(code)))
        for action in self._language_menu.actions():
            action.setChecked(action.data() == code)

    def _sync_header(self, state: FlyoutState) -> None:
        if state.server_ok is None:
            text, object_name = CHECKING_STATUS, "cardDescription"
        elif state.server_ok:
            text, object_name = f"{OK_GLYPH} {state.server_message}", "statusOk"
        else:
            text, object_name = f"{WARNING_GLYPH} {state.server_message}", "statusWarn"
        self._status_label.setText(text)
        set_object_name(self._status_label, object_name)

    def _sync_app_card(self, state: FlyoutState) -> None:
        has_app = bool(state.current_app)
        show_enable = has_app and state.current_app_disabled
        self._app_name.setText(state.current_app if has_app else NO_APP_TEXT)
        self._app_status.setText(state.current_app_status)
        self._app_status.setVisible(has_app and bool(state.current_app_status))
        self._disable_app_button.setVisible(not show_enable)
        self._disable_app_button.setEnabled(has_app)
        self._enable_app_button.setVisible(show_enable)

    def _restyle(self, accent: str) -> None:
        apply_style(self, accent)
        tokens = current_tokens()
        fill = readable_accent(accent, tokens)
        on_fill = "#000000" if tokens is DARK else "#ffffff"
        self._badge.setStyleSheet(
            f"background: {fill}; color: {on_fill}; border-radius: {BADGE_SIZE // 2}px;"
            " font-weight: 600;"
        )
        self._sync_header(self._state)

    # ----- user actions -----------------------------------------------------

    def _finish(self, emit: Callable[[], None]) -> None:
        """Emit the signal for a one-shot action, then close the flyout."""
        emit()
        self.hide()

    def _on_enabled_clicked(self, checked: bool) -> None:
        self.set_state(replace(self._state, enabled=checked))
        self.enabled_toggled.emit(checked)

    def _on_picky_clicked(self, checked: bool) -> None:
        self.set_state(replace(self._state, picky=checked))
        self.picky_toggled.emit(checked)

    def _on_pause_clicked(self) -> None:
        if self._state.paused_until:
            self._finish(self.resume_requested.emit)
        else:
            self._finish(self.pause_requested.emit)

    def _on_language_tile_clicked(self) -> None:
        below_tile = QPoint(0, self._language_tile.height())
        self._language_menu.popup(self._language_tile.mapToGlobal(below_tile))

    def _on_language_action(self, action: QAction) -> None:
        self._choose_language(str(action.data()))

    def _choose_language(self, code: str) -> None:
        # The flyout stays open so the subtitle can update.
        self.set_state(replace(self._state, language=code))
        self.language_chosen.emit(code)

    def _on_disable_app_clicked(self) -> None:
        app = self._state.current_app
        self._finish(lambda: self.disable_app_requested.emit(app))

    def _on_enable_app_clicked(self) -> None:
        app = self._state.current_app
        self._finish(lambda: self.enable_app_requested.emit(app))

    def _on_add_field_clicked(self) -> None:
        self._finish(self.pick_field_requested.emit)

    def _on_settings_clicked(self) -> None:
        self._finish(self.settings_requested.emit)

    def _on_quit_clicked(self) -> None:
        self._finish(self.quit_requested.emit)
