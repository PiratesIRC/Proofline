"""The issues popup.

Frameless, always on top, and never takes keyboard focus, so the text field the user
is typing in keeps focus while they click a correction. Styled with the ui_kit tokens
and accent colour like the rest of the app.

Permanent actions (add a word, turn off a rule, app or window) show a notice with Undo
inside the popup; the popup emits undo_requested(config field, value) for the app to
remove that value again.

Dragging the popup pins it: it stays where it was dropped and stays open until Close is
clicked, showing a short status line while the field has nothing to list.
"""

from __future__ import annotations

import html
import logging
import re

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QHideEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from proofline.config import DEFAULT_TRAY_COLOR
from proofline.dictionary import is_spelling_match
from proofline.lt_client import Match
from proofline.non_activating import make_non_activating
from proofline.ui_kit import Tokens, apply_style, current_tokens, link_button

log = logging.getLogger(__name__)

POPUP_WIDTH = 360
POPUP_MAX_HEIGHT = 420
MAX_LISTED_MATCHES = 25
FIXES_PER_ROW = 3
EXCERPT_CONTEXT_CHARS = 32
NOTICE_ONLY_MS = 10_000
ELLIPSIS = "…"
MORE_CLOSED = "More options ▾"
MORE_OPEN = "More options ▴"
CLOSE_GLYPH = "✕"
IGNORE_TEXT = "Ignore for now"
ADD_WORD_TEXT = "Add to dictionary"
DISABLE_RULE_TEXT = "Turn off this rule"
UNDO_TEXT = "Undo"
NO_ISSUES_TEXT = "No issues found."
DRAG_TOOLTIP = "Drag to move. A moved popup stays open until you close it."
WHITESPACE = re.compile(r"\s+")

POPUP_EXTRA_STYLE = """
QFrame#popup {{ background: {t.card}; border: 1px solid {t.input_border}; border-radius: 8px; }}
QWidget#uiRoot QLabel#popupHeader {{ font-size: 14px; font-weight: 600; }}
QWidget#uiRoot QLabel#issueTitle {{ font-weight: 600; }}
QFrame#issueRow {{ border: none; border-top: 1px solid {t.divider}; }}
QFrame#issueRowFirst {{ border: none; }}
QPushButton#closeButton {{ background: transparent; border: none; color: {t.secondary}; padding: 2px 6px; }}
QPushButton#closeButton:hover {{ background: {t.hover}; }}
QPushButton#linkButton {{ padding: 2px 0; }}
QPushButton#linkButton:hover {{ text-decoration: underline; }}
"""


def popup_extra_style(tokens: Tokens) -> str:
    return POPUP_EXTRA_STYLE.format(t=tokens)


def issue_count_text(count: int) -> str:
    if count == 0:
        return "No issues"
    return f"{count} issue" + ("" if count == 1 else "s")


def match_excerpt(text: str, match: Match, context: int = EXCERPT_CONTEXT_CHARS) -> tuple[str, str, str] | None:
    """(before, flagged, after) around the match, whitespace collapsed, cut at word edges.

    None when the text no longer holds the flagged words at the match offset.
    """
    start, end = match.offset, match.offset + match.length
    if not text or text[start:end] != match.error_text or not match.error_text:
        return None
    before, after = text[max(0, start - context):start], text[end:end + context]
    if start > context:
        before = ELLIPSIS + before.split(" ", 1)[-1]
    if end + context < len(text):
        after = after.rsplit(" ", 1)[0] + ELLIPSIS
    return WHITESPACE.sub(" ", before), WHITESPACE.sub(" ", match.error_text), WHITESPACE.sub(" ", after)


class IssuesPopup(QWidget):
    """Lists issues with one button per suggested replacement."""

    replacement_chosen = pyqtSignal(object, str)  # Match, replacement
    ignore_requested = pyqtSignal(object)  # Match
    add_word_requested = pyqtSignal(object)  # Match
    disable_rule_requested = pyqtSignal(object)  # Match
    disable_app_requested = pyqtSignal()
    disable_window_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    undo_requested = pyqtSignal(str, str)  # config field, value to remove

    def __init__(self) -> None:
        super().__init__()
        make_non_activating(self)
        self.setObjectName("uiRoot")
        self.setFixedWidth(POPUP_WIDTH)
        self._accent = DEFAULT_TRAY_COLOR
        self._tokens = current_tokens()
        self._style_key: tuple[Tokens, str] | None = None
        self._shown: tuple[tuple[Match, ...], str] | None = None  # what the rows were built from
        self._text = ""
        self._anchor = QRect()
        self._bounds = QRect()
        self._undo: tuple[str, str] | None = None
        self._press_offset: QPoint | None = None  # cursor minus top-left while the button is down
        self._pinned = False
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self.hide)

        self._frame = QFrame(self)
        self._frame.setObjectName("popup")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        layout = QVBoxLayout(self._frame)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.addLayout(self._build_header())
        layout.addWidget(self._build_notice())
        layout.addWidget(self._build_list())
        layout.addWidget(self._build_footer())
        self._apply_style()

    @property
    def is_notice_only(self) -> bool:
        """True while the popup shows only an Undo notice (after turning off an app or window)."""
        return self.isVisible() and self._header.isHidden()

    @property
    def is_pinned(self) -> bool:
        """True after the user dragged the open popup; it then closes only through Close."""
        return self.isVisible() and self._pinned

    @property
    def notice_text(self) -> str:
        return self._notice_label.text() if not self._notice.isHidden() else ""

    # ----- construction -----------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        self._header = QLabel()
        self._header.setObjectName("popupHeader")
        self._header.setToolTip(DRAG_TOOLTIP)
        self._header.setCursor(Qt.CursorShape.SizeAllCursor)
        close_button = QPushButton(CLOSE_GLYPH)
        close_button.setObjectName("closeButton")
        close_button.setAccessibleName("Close")
        close_button.setToolTip("Close")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addWidget(self._header)
        row.addStretch(1)  # keeps Close on the right while the header is hidden
        row.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignTop)
        return row

    def _build_notice(self) -> QFrame:
        self._notice = QFrame()
        self._notice.setObjectName("info_success")
        self._notice_label = QLabel()
        self._notice_label.setWordWrap(True)
        undo = link_button(UNDO_TEXT)
        undo.clicked.connect(self._on_undo)
        row = QHBoxLayout(self._notice)
        row.setContentsMargins(10, 6, 10, 6)
        row.addWidget(self._notice_label, stretch=1)
        row.addWidget(undo)
        self._notice.hide()
        return self._notice

    def _build_list(self) -> QScrollArea:
        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._list)
        return self._scroll

    def _build_footer(self) -> QWidget:
        self._footer = QWidget()
        self._more_button = link_button(MORE_CLOSED)
        self._more_button.clicked.connect(lambda: self._set_more_open(self._more.isHidden()))
        self._disable_app_button = link_button("")
        self._disable_app_button.clicked.connect(self.disable_app_requested.emit)
        self._disable_window_button = link_button("Turn off in this window")
        self._disable_window_button.clicked.connect(self.disable_window_requested.emit)
        settings_button = link_button("Settings…")
        settings_button.clicked.connect(self.settings_requested.emit)
        self._more = QWidget()
        more_layout = QVBoxLayout(self._more)
        more_layout.setContentsMargins(12, 0, 0, 0)
        more_layout.setSpacing(2)
        for button in (self._disable_app_button, self._disable_window_button, settings_button):
            more_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._more.hide()
        layout = QVBoxLayout(self._footer)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._more_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._more)
        return self._footer

    # ----- public API -------------------------------------------------------

    def show_issues(
        self, matches: tuple[Match, ...], app_name: str, anchor: QRect, bounds: QRect,
        text: str = "", accent: str = DEFAULT_TRAY_COLOR,
    ) -> None:
        """Show matches beside the badge at anchor. text is the checked field text, for excerpts."""
        self._accent, self._text, self._anchor, self._bounds = accent, text, anchor, bounds
        self._notice_timer.stop()
        restyled = self._apply_style()  # the theme or accent may have changed since the last time
        self._disable_app_button.setText(f"Turn off in {app_name}")
        self._header.setText(issue_count_text(len(matches)))
        self._header.show()
        self._scroll.show()
        self._footer.show()
        if restyled or self._shown != (matches, text):  # rows carry theme colours and the text
            self._populate(matches)
            self._shown = (matches, text)
        self._refit()
        self.show()
        self.raise_()

    def show_notice(self, message: str, field: str, value: str) -> None:
        """Show message with an Undo that emits undo_requested(field, value)."""
        self._undo = (field, value)
        self._notice_label.setText(message)
        self._notice.show()
        if self.isVisible():
            self._refit()

    def show_notice_only(self, message: str, field: str, value: str) -> None:
        """Replace the issues with just the notice; the popup closes itself after a while."""
        self._header.hide()
        self._scroll.hide()
        self._footer.hide()
        self.show_notice(message, field, value)
        if not self.is_pinned:
            self._notice_timer.start(NOTICE_ONLY_MS)

    def show_status(self, message: str) -> None:
        """A pinned popup whose issues no longer apply: show message instead of the list."""
        self._header.setText(message)
        self._header.show()
        self._scroll.hide()
        self._footer.hide()
        self._shown = None
        self._refit()

    # ----- internals --------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Buttons take their own clicks; presses on labels and the background arrive here.
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_offset is None:
            return
        target = event.globalPosition().toPoint() - self._press_offset
        if not self._pinned and (target - self.pos()).manhattanLength() < QApplication.startDragDistance():
            return
        self._pinned = True
        self._notice_timer.stop()
        self.move(target)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_offset = None

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._pinned = False
        self._press_offset = None
        self._notice_timer.stop()
        self._undo = None
        self._notice.hide()
        self._set_more_open(False)

    def _apply_style(self) -> bool:
        """Restyle when the theme or accent changed (style sheets resolve colours once)."""
        key = (current_tokens(), self._accent)
        if key == self._style_key:
            return False
        self._style_key = key
        self._tokens = apply_style(self, self._accent, popup_extra_style)
        return True

    def _set_more_open(self, open_: bool) -> None:
        self._more.setVisible(open_)
        self._more_button.setText(MORE_OPEN if open_ else MORE_CLOSED)
        if self.isVisible():
            self._refit()

    def _on_undo(self) -> None:
        if self._undo is None:
            return
        field, value = self._undo
        self._undo = None
        self._notice.hide()
        notice_only = self.is_notice_only
        self.undo_requested.emit(field, value)
        if notice_only:
            self.hide()
        elif self.isVisible():
            self._refit()

    def _refit(self) -> None:
        self._fit_list_height()
        # Shown/hidden children only change the layout on the next event loop pass; recompute
        # now so the popup can also shrink (e.g. to just the Undo notice).
        self._frame.layout().activate()
        self.layout().activate()
        self.resize(POPUP_WIDTH, self.sizeHint().height())
        if not self.is_pinned:  # a dragged popup stays where the user dropped it
            self.move(_popup_position(self._anchor, self.size().width(), self.size().height(), self._bounds))

    def _fit_list_height(self) -> None:
        """Size the scroll area to its rows, up to POPUP_MAX_HEIGHT. QScrollArea caches
        its content size, so its own size hint goes stale when the rows change while
        the popup is open."""
        margins = self._frame.layout().contentsMargins()
        width = POPUP_WIDTH - margins.left() - margins.right()
        height = self._list.heightForWidth(width)
        if height < 0:
            height = self._list.sizeHint().height()
        self._scroll.setFixedHeight(min(height, POPUP_MAX_HEIGHT))

    def _populate(self, matches: tuple[Match, ...]) -> None:
        while (item := self._list_layout.takeAt(0)) is not None:
            if item.widget():
                item.widget().hide()  # deleteLater() only runs after this update is drawn
                item.widget().deleteLater()
        if not matches:
            self._add_row(QLabel(NO_ISSUES_TEXT))
        for index, match in enumerate(matches[:MAX_LISTED_MATCHES]):
            self._add_row(self._match_row(match, first=index == 0))
        if len(matches) > MAX_LISTED_MATCHES:
            hidden = len(matches) - MAX_LISTED_MATCHES
            self._add_row(QLabel(f"…and {hidden} more. Fix these first."))
        self._list_layout.addStretch()

    def _add_row(self, row: QWidget) -> None:
        self._list_layout.addWidget(row)
        # Widgets added to a visible popup are only shown on the next event loop pass, and
        # adjustSize() skips hidden ones, which squashed the list when results updated.
        row.show()

    def _match_row(self, match: Match, first: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("issueRowFirst" if first else "issueRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        title = QLabel(match.short_message or match.category or "Possible issue")
        title.setObjectName("issueTitle")
        message = QLabel(match.message)
        message.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(message)
        layout.addWidget(self._excerpt_label(match))
        layout.addLayout(self._fix_buttons(match))
        layout.addLayout(self._action_row(match))
        return row

    def _excerpt_label(self, match: Match) -> QLabel:
        flagged_style = f"color: {self._tokens.error_text}; font-weight: 600; text-decoration: underline;"
        parts = match_excerpt(self._text, match)
        before, flagged, after = parts if parts else ("", WHITESPACE.sub(" ", match.error_text), "")
        label = QLabel(
            f"{html.escape(before, quote=False)}<span style='{flagged_style}'>{html.escape(flagged, quote=False)}"
            f"</span>{html.escape(after, quote=False)}"
        )
        label.setObjectName("cardDescription")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        return label

    def _fix_buttons(self, match: Match) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for index, replacement in enumerate(match.replacements):
            button = QPushButton(replacement or "(remove)")
            button.setObjectName("accentButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, m=match, r=replacement: self.replacement_chosen.emit(m, r)
            )
            grid.addWidget(button, index // FIXES_PER_ROW, index % FIXES_PER_ROW)
        if not match.replacements:
            hint = QLabel("No suggestion")
            hint.setObjectName("cardDescription")
            grid.addWidget(hint, 0, 0)
        grid.setColumnStretch(FIXES_PER_ROW, 1)
        return grid

    def _action_row(self, match: Match) -> QHBoxLayout:
        actions = [(IGNORE_TEXT, self.ignore_requested)]
        if is_spelling_match(match):
            actions.append((ADD_WORD_TEXT, self.add_word_requested))
        if match.rule_id:
            actions.append((DISABLE_RULE_TEXT, self.disable_rule_requested))
        row = QHBoxLayout()
        row.setSpacing(14)
        for label, signal in actions:
            button = link_button(label)
            button.clicked.connect(lambda _checked=False, s=signal, m=match: s.emit(m))
            row.addWidget(button)
        row.addStretch()
        return row


def _popup_position(anchor: QRect, width: int, height: int, bounds: QRect) -> QPoint:
    """Right-align with the badge, above it if it fits, otherwise below; keep on screen."""
    x = anchor.right() - width
    y = anchor.top() - height - 4
    if y < bounds.top():
        y = anchor.bottom() + 4
    x = max(bounds.left(), min(x, bounds.right() - width))
    y = max(bounds.top(), min(y, bounds.bottom() - height))
    return QPoint(x, y)
