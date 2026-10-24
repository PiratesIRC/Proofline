"""Small Windows-11-style widget kit shared by the Settings window and the tray flyout.

- Colour tokens for light and dark, and a style sheet built from them plus the accent.
- ToggleSwitch: an on/off pill (Qt has no native switch).
- SettingCard: title + description on the left, controls on the right.
- ExpanderCard: a card whose body folds open (lists, advanced options).
- InfoBar: a coloured notice with a title and message (warning / error / success).

Style sheets resolve colours once, so call apply_style() again after a theme change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SWITCH_SIZE = QSize(40, 20)
KNOB_ON_PX = 12
KNOB_OFF_PX = 10
CARD_MIN_HEIGHT = 48
# Flyout tiles are 64 px: 42 px of text area + 2 x 10 px padding + 2 x 1 px border. It has to be
# a style rule: the sheet's QPushButton min-height overrides setMinimumHeight().
TILE_CONTENT_MIN_PX = 42
CHEVRON_OPEN = "▴"
CHEVRON_CLOSED = "▾"


@dataclass(frozen=True)
class Tokens:
    window: str
    card: str
    card_border: str
    text: str
    secondary: str
    input_bg: str
    input_border: str
    hover: str
    selected: str
    divider: str
    warning_bg: str
    warning_border: str
    error_bg: str
    error_border: str
    success_bg: str
    success_border: str
    success_text: str
    warning_text: str
    error_text: str
    off_track: str


LIGHT = Tokens(
    window="#f3f3f3", card="#fbfbfb", card_border="#e5e5e5", text="#1a1a1a", secondary="#5c5c5c",
    input_bg="#ffffff", input_border="#d0d0d0", hover="#eaeaea", selected="#e6e6e6", divider="#ededed",
    warning_bg="#fff4ce", warning_border="#f2e2a8", error_bg="#fde7e9", error_border="#f4c2c7",
    success_bg="#dff6dd", success_border="#bfe5bb", success_text="#0f6d1a", warning_text="#a65a00", error_text="#c42b1c",
    off_track="#5c5c5c",
)
DARK = Tokens(
    window="#202020", card="#2b2b2b", card_border="#1d1d1d", text="#ffffff", secondary="#c5c5c5",
    input_bg="#2d2d2d", input_border="#3c3c3c", hover="#323232", selected="#2d2d2d", divider="#1d1d1d",
    warning_bg="#433519", warning_border="#5a4a22", error_bg="#442726", error_border="#5c3433",
    success_bg="#393d1b", success_border="#4b5226", success_text="#6ccb5f", warning_text="#ffb454", error_text="#ff99a4",
    off_track="#c5c5c5",
)
SEVERITIES = ("warning", "error", "success")


def current_tokens() -> Tokens:
    hints = QGuiApplication.styleHints()
    return DARK if hints is not None and hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT


def readable_accent(accent: str, tokens: Tokens) -> str:
    """Lighten the accent on dark backgrounds so text and fills on it stay legible."""
    return QColor(accent).lighter(170).name() if tokens is DARK else accent


def stylesheet(tokens: Tokens, accent: str) -> str:
    t = tokens
    fill = readable_accent(accent, t)
    on_fill = "#000000" if t is DARK else "#ffffff"
    return f"""
    QWidget#uiRoot {{ background: {t.window}; color: {t.text}; }}
    QWidget#uiRoot QLabel {{ color: {t.text}; background: transparent; }}
    QLabel#pageTitle {{ font-size: 26px; font-weight: 600; }}
    QLabel#groupTitle {{ font-size: 14px; font-weight: 600; padding-top: 10px; }}
    QLabel#cardTitle {{ font-size: 14px; }}
    QLabel#cardDescription, QLabel#hint {{ font-size: 12px; color: {t.secondary}; }}
    QWidget#uiRoot QLabel#statusOk {{ font-size: 12px; color: {t.success_text}; }}
    QWidget#uiRoot QLabel#statusWarn {{ font-size: 12px; color: {t.warning_text}; }}
    QWidget#uiRoot QLabel#statusError {{ font-size: 12px; color: {t.error_text}; }}
    QFrame#card {{ background: {t.card}; border: 1px solid {t.card_border}; border-radius: 6px; }}
    QFrame#cardBody {{ border-top: 1px solid {t.divider}; }}
    QFrame#flyoutPanel {{ background: {t.card}; border: none; }}
    QFrame#info_warning {{ background: {t.warning_bg}; border: 1px solid {t.warning_border}; border-radius: 6px; }}
    QFrame#info_error {{ background: {t.error_bg}; border: 1px solid {t.error_border}; border-radius: 6px; }}
    QFrame#info_success {{ background: {t.success_bg}; border: 1px solid {t.success_border}; border-radius: 6px; }}
    QListWidget#nav {{ background: transparent; border: none; font-size: 14px; outline: none; }}
    QListWidget#nav::item {{ height: 36px; padding-left: 10px; border-radius: 4px; color: {t.text}; }}
    QListWidget#nav::item:hover {{ background: {t.hover}; }}
    QListWidget#nav::item:selected {{ background: {t.selected}; color: {t.text}; border-left: 3px solid {fill}; }}
    QLineEdit, QComboBox, QSpinBox {{
        background: {t.input_bg}; color: {t.text}; border: 1px solid {t.input_border};
        border-radius: 4px; padding: 4px 8px; min-height: 22px;
    }}
    QListWidget {{ background: {t.input_bg}; color: {t.text}; border: 1px solid {t.input_border}; border-radius: 4px; }}
    QPushButton {{
        background: {t.card}; color: {t.text}; border: 1px solid {t.input_border};
        border-radius: 4px; padding: 5px 14px; min-height: 20px;
    }}
    QPushButton:hover {{ background: {t.hover}; }}
    QPushButton:disabled {{ color: {t.secondary}; }}
    QPushButton#accentButton {{ background: {fill}; color: {on_fill}; border: none; font-weight: 600; }}
    QPushButton#accentButton:disabled {{
        background: {t.card}; color: {t.secondary}; border: 1px solid {t.input_border}; font-weight: 400;
    }}
    QPushButton#linkButton {{ background: transparent; border: none; color: {fill}; padding: 4px 0; }}
    QPushButton#tile {{
        background: {t.card}; border: 1px solid {t.card_border}; border-radius: 6px;
        text-align: left; padding: 10px 12px; min-height: {TILE_CONTENT_MIN_PX}px;
    }}
    QPushButton#tile:checked {{ background: {fill}; color: {on_fill}; border: none; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


def apply_style(widget: QWidget, accent: str, extra: Callable[[Tokens], str] | None = None) -> Tokens:
    """(Re)apply the kit's style sheet, plus extra(tokens) rules if given; returns the tokens used."""
    tokens = current_tokens()
    widget.setObjectName(widget.objectName() or "uiRoot")
    widget.setStyleSheet("")
    widget.setStyleSheet(stylesheet(tokens, accent) + (extra(tokens) if extra else ""))
    # Rich-text links take their colour from each label's own palette (the label rule above
    # gives every label its own), not from the style sheet or the window.
    link = QColor(readable_accent(accent, tokens))
    for label in widget.findChildren(QLabel):
        if label.openExternalLinks():
            palette = label.palette()
            palette.setColor(QPalette.ColorRole.Link, link)
            palette.setColor(QPalette.ColorRole.LinkVisited, link)
            label.setPalette(palette)
    for switch in widget.findChildren(ToggleSwitch):
        switch.set_colors(readable_accent(accent, tokens), tokens.off_track)
    return tokens


def set_object_name(widget: QWidget, name: str) -> None:
    """Change an objectName and re-polish so the style sheet picks up the new name."""
    if widget.objectName() == name:
        return
    widget.setObjectName(name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def link_button(text: str) -> QPushButton:
    """A flat button drawn as an accent-coloured link."""
    button = QPushButton(text)
    button.setObjectName("linkButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ToggleSwitch(QAbstractButton):
    """A Windows-style on/off switch. Use `toggled(bool)` like a checkbox."""

    def __init__(self, accessible_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(accessible_name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._on_color = QColor("#2e7d32")
        self._off_color = QColor("#5c5c5c")

    def set_colors(self, on_color: str, off_color: str) -> None:
        self._on_color = QColor(on_color)
        self._off_color = QColor(off_color)
        self.update()

    def sizeHint(self) -> QSize:
        return SWITCH_SIZE

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = SWITCH_SIZE.width(), SWITCH_SIZE.height()
        track = QRectF(0.5, 0.5, w - 1, h - 1)
        radius = (h - 1) / 2
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._on_color)
            painter.drawRoundedRect(track, radius, radius)
            knob, x, color = KNOB_ON_PX, w - 4 - KNOB_ON_PX, QColor("white" if self._on_color.lightness() < 160 else "black")
        else:
            painter.setPen(QPen(self._off_color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track, radius, radius)
            knob, x, color = KNOB_OFF_PX, 5, self._off_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(x, (h - knob) / 2, knob, knob))
        if self.hasFocus():
            painter.setPen(QPen(self._on_color, 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track, radius, radius)
        painter.end()


def _text_column(title: str, description: str) -> tuple[QVBoxLayout, QLabel, QLabel]:
    title_label = QLabel(title)
    title_label.setObjectName("cardTitle")
    description_label = QLabel(description)
    description_label.setObjectName("cardDescription")
    description_label.setWordWrap(True)
    if not description:
        # Only ever hide here: showing a label that has no parent yet opens it as a top-level
        # window for a moment (seen as small windows flashing at startup).
        description_label.hide()
    column = QVBoxLayout()
    column.setSpacing(1)
    column.addWidget(title_label)
    column.addWidget(description_label)
    return column, title_label, description_label


class SettingCard(QFrame):
    """One setting: title and description on the left, controls on the right."""

    def __init__(self, title: str, description: str = "", *controls: QWidget, keywords: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(CARD_MIN_HEIGHT)
        self._keywords = f"{title} {description} {keywords}".casefold()
        column, self.title_label, self.description_label = _text_column(title, description)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(16, 10, 16, 10)
        self._row.setSpacing(12)
        self._row.addLayout(column, stretch=1)
        for control in controls:
            self.add_control(control)

    def add_control(self, control: QWidget) -> None:
        self._row.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_description(self, text: str) -> None:
        self.description_label.setText(text)
        self.description_label.setVisible(bool(text))

    def matches(self, query: str) -> bool:
        return query.casefold() in self._keywords


class ExpanderCard(QFrame):
    """A card with a header that folds a body open and closed."""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, description: str = "", keywords: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self._keywords = f"{title} {description} {keywords}".casefold()
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.mousePressEvent = self._on_header_click  # type: ignore[method-assign]
        column, self.title_label, self.description_label = _text_column(title, description)
        self._summary = QLabel()
        self._summary.setObjectName("cardDescription")
        self._chevron = QLabel(CHEVRON_CLOSED)
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 10, 16, 10)
        row.addLayout(column, stretch=1)
        row.addWidget(self._summary)
        row.addWidget(self._chevron)

        self.body = QFrame()
        self.body.setObjectName("cardBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(16, 10, 16, 14)
        self.body.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.body)

    @property
    def is_expanded(self) -> bool:
        return not self.body.isHidden()

    def set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self._chevron.setText(CHEVRON_OPEN if expanded else CHEVRON_CLOSED)
        self.toggled.emit(expanded)

    def set_summary(self, text: str) -> None:
        self._summary.setText(text)

    def matches(self, query: str) -> bool:
        return query.casefold() in self._keywords

    def _on_header_click(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_expanded(not self.is_expanded)


class InfoBar(QFrame):
    """Coloured notice; severity is 'warning', 'error' or 'success'."""

    def __init__(self, severity: str = "warning", title: str = "", message: str = "") -> None:
        super().__init__()
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: 600;")
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.addWidget(self._title, alignment=Qt.AlignmentFlag.AlignTop)
        row.addWidget(self._message, stretch=1)
        self.show_message(severity, title, message)

    def show_message(self, severity: str, title: str, message: str) -> None:
        if severity not in SEVERITIES:
            raise ValueError(f"Unknown severity {severity!r}")
        set_object_name(self, f"info_{severity}")
        self.severity = severity
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._message.setText(message)

    @property
    def message(self) -> str:
        return self._message.text()
