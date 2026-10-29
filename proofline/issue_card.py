"""A small card under a flagged word, shown while the caret is inside that word.

It offers the first suggestions, Ignore, Add to dictionary for spelling, Rephrase (when AI is
available), and a link to the full issues popup. While a rephrase runs it shows the sentence,
"Asking the AI...", then the rewordings or a one-line message. Like the popup it never takes
focus, so the caret stays in the field.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proofline.ai_diff import changed_words_html
from proofline.config import DEFAULT_TRAY_COLOR
from proofline.dictionary import is_spelling_match
from proofline.lt_client import Match
from proofline.non_activating import make_non_activating
from proofline.overlay_widgets import ADD_WORD_TEXT, button_text, offered_replacements
from proofline.ui_kit import (
    Tokens,
    apply_style,
    current_tokens,
    link_button,
    readable_accent,
)

CARD_WIDTH = 260
CARD_GAP = 6  # between the word and the card
CARD_MARGIN = 8
FRAME_BORDER = 1  # QFrame#issueCard's style-sheet border, per side
FIRST_FIX_TINT = 0.16  # accent opacity behind the first suggestion
MAX_CARD_FIXES = 3
OPTION_PADDING = 6  # inside an option button, around its text
OPTION_BUTTON_WIDTH = CARD_WIDTH - 2 * (CARD_MARGIN + FRAME_BORDER)
SENTENCE_PREVIEW_CHARS = 80
IGNORE_TEXT = "Ignore"
ALL_ISSUES_TEXT = "All issues…"
REPHRASE_TEXT = "AI Rephrase"
WAITING_TEXT = "Asking the AI..."
CANCEL_TEXT = "Cancel"
RETRY_TEXT = "Retry"
CLOSE_TEXT = "Close"

CARD_EXTRA_STYLE = """
QFrame#issueCard {{ background: {t.card}; border: 1px solid {t.input_border}; border-radius: 8px; }}
QWidget#uiRoot QLabel#cardTitle {{ font-size: 12px; color: {t.secondary}; }}
QWidget#uiRoot QLabel#cardSentence {{ font-size: 12px; color: {t.secondary}; font-style: italic; }}
QWidget#uiRoot QLabel#cardOptionText {{ font-size: 14px; font-weight: 400; color: {accent};
    background: transparent; }}
QPushButton#cardFix {{ background: transparent; border: none; border-radius: 6px; color: {accent};
    font-size: 15px; font-weight: 600; padding: 4px 6px; text-align: left; }}
QPushButton#cardFix:hover {{ background: {t.hover}; }}
QPushButton#cardFirstFix {{ background: {tint}; border: none; border-radius: 6px; color: {accent};
    font-size: 16px; font-weight: 700; padding: 6px; text-align: left; }}
QPushButton#cardFirstFix:hover {{ background: {t.hover}; }}
QPushButton#linkButton:hover {{ text-decoration: underline; }}
"""


def card_position(word: QRect, size: QRect, bounds: QRect) -> QPoint:
    """Below the word, left-aligned with it; above it when there is no room below; on screen."""
    x = max(bounds.left(), min(word.left(), bounds.left() + bounds.width() - size.width()))
    y = word.top() + word.height() + CARD_GAP  # QRect.bottom() is one pixel short
    if y + size.height() > bounds.top() + bounds.height():
        y = word.top() - CARD_GAP - size.height()
    return QPoint(x, max(bounds.top(), y))


def short_sentence(sentence: str, limit: int = SENTENCE_PREVIEW_CHARS) -> str:
    """The sentence on one line, cut to limit characters with an ellipsis."""
    flat = " ".join(sentence.split())
    return flat if len(flat) <= limit else flat[:limit - 1] + "\u2026"


class IssueCard(QWidget):
    replacement_chosen = pyqtSignal(object, str)  # Match, replacement
    ignore_requested = pyqtSignal(object)  # Match
    add_word_requested = pyqtSignal(object)  # Match
    all_issues_requested = pyqtSignal()
    rephrase_requested = pyqtSignal(object)  # Match; the card stays open
    rephrase_cancelled = pyqtSignal()  # Cancel or Close
    rephrase_retry = pyqtSignal()
    rephrase_chosen = pyqtSignal(str)  # the chosen wording

    def __init__(self) -> None:
        super().__init__()
        make_non_activating(self)
        self.setObjectName("uiRoot")
        self.setFixedWidth(CARD_WIDTH)
        self._match: Match | None = None
        self._ai_available = False
        self._rephrasing = False
        self._sentence = ""
        self._anchor = QRect()
        self._bounds = QRect()
        self._accent = DEFAULT_TRAY_COLOR
        self._style_key: tuple[Tokens, str] | None = None
        self._frame = QFrame(self)
        self._frame.setObjectName("issueCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        self._layout = QVBoxLayout(self._frame)
        self._layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        self._layout.setSpacing(2)

    @property
    def match(self) -> Match | None:
        """The flagged issue on show, or None while hidden or showing a rephrase."""
        return self._match if self.isVisible() and not self._rephrasing else None

    def show_for(
        self, match: Match, word: QRect, bounds: QRect, accent: str = DEFAULT_TRAY_COLOR,
        ai_available: bool = False,
    ) -> None:
        """Show match's fixes next to word (logical screen rectangle), inside bounds."""
        same = (match, accent, ai_available) == (self._match, self._accent, self._ai_available)
        if self.isVisible() and same and not self._rephrasing:
            return
        self._match, self._accent, self._ai_available = match, accent, ai_available
        self._rephrasing = False
        self._anchor, self._bounds = QRect(word), QRect(bounds)
        self._rebuild(match)
        self._present()

    def show_waiting(self, sentence: str, anchor: QRect, bounds: QRect, accent: str) -> None:
        """Start a rephrase: the sentence, "Asking the AI..." and Cancel, under anchor."""
        self._enter_rephrase(anchor, bounds, accent)
        self._sentence = sentence
        self._clear_card()
        self._add_rephrase_header()
        self._layout.addWidget(self._label(WAITING_TEXT))
        self._layout.addLayout(self._link_row([(CANCEL_TEXT, self._cancel)]))
        self._present()

    def show_options(self, options: tuple[str, ...], sentence: str) -> None:
        """The rewordings, changed words in bold; clicking one emits rephrase_chosen."""
        self._rephrasing = True
        self._sentence = sentence
        self._clear_card()
        self._apply_style()  # before the buttons measure their text in the styled font
        self._add_rephrase_header()
        for option in options:
            self._layout.addWidget(self._option_button(option, sentence))
        self._layout.addLayout(self._link_row([(CANCEL_TEXT, self._cancel)]))
        self._present()

    def show_message(
        self, message: str, retry: bool, anchor: QRect | None = None, bounds: QRect | None = None,
        accent: str | None = None,
    ) -> None:
        """One line instead of the rewordings; with anchor, the card opens there by itself."""
        if anchor is not None and bounds is not None:
            self._enter_rephrase(anchor, bounds, accent or self._accent)
            self._sentence = ""
        self._rephrasing = True
        self._clear_card()
        self._add_rephrase_header()
        text = self._label(message)
        text.setWordWrap(True)
        self._layout.addWidget(text)
        links = [(RETRY_TEXT, self.rephrase_retry.emit)] if retry else []
        self._layout.addLayout(self._link_row([*links, (CLOSE_TEXT, self._cancel)]))
        self._present()

    def _enter_rephrase(self, anchor: QRect, bounds: QRect, accent: str) -> None:
        self._rephrasing = True
        self._anchor, self._bounds, self._accent = QRect(anchor), QRect(bounds), accent

    def _present(self) -> None:
        self._apply_style()
        # Children added while visible start hidden. This re-shows every child: hide parts by
        # rebuilding the card without them, never with hide().
        for child in self._frame.findChildren(QWidget):
            child.show()
        self._layout.activate()
        self.layout().activate()
        self.resize(CARD_WIDTH, self.sizeHint().height())
        self.move(card_position(self._anchor, self.rect(), self._bounds))
        self.show()
        self.raise_()

    def _apply_style(self) -> None:
        key = (current_tokens(), self._accent)
        if key != self._style_key:
            self._style_key = key
            apply_style(self, self._accent, self._extra_style)

    def _extra_style(self, tokens: Tokens) -> str:
        accent = QColor(readable_accent(self._accent, tokens))
        tint = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, {FIRST_FIX_TINT})"
        return CARD_EXTRA_STYLE.format(t=tokens, accent=accent.name(), tint=tint)

    def _clear_card(self) -> None:
        while (item := self._layout.takeAt(0)) is not None:
            if item.widget():
                _discard(item.widget())
            elif item.layout():
                _clear(item.layout())

    def _rebuild(self, match: Match) -> None:
        self._clear_card()
        title = QLabel(match.short_message or match.category or "Possible issue")
        title.setObjectName("cardTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        self._layout.addWidget(title)
        if not match.replacements:
            message = QLabel(match.message)
            message.setTextFormat(Qt.TextFormat.PlainText)
            message.setWordWrap(True)
            self._layout.addWidget(message)
        for index, replacement in enumerate(offered_replacements(match)[:MAX_CARD_FIXES]):
            button = QPushButton(button_text(replacement))
            button.setObjectName("cardFirstFix" if index == 0 else "cardFix")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # Rich text so the escaped quotes and ampersands display as typed (plain text would show &quot;).
            button.setToolTip(f"<p>{html.escape(match.message)}</p>")
            button.clicked.connect(lambda _checked=False, r=replacement: self._choose(r))
            self._layout.addWidget(button)
        if self._ai_available:  # its own row: four links do not fit across the card
            self._layout.addLayout(self._link_row([(REPHRASE_TEXT, lambda: self.rephrase_requested.emit(match))]))
        self._layout.addLayout(self._action_row(match))

    def _action_row(self, match: Match) -> QHBoxLayout:
        actions = [(IGNORE_TEXT, lambda: self._emit_and_hide(self.ignore_requested))]
        if is_spelling_match(match):
            actions.append((ADD_WORD_TEXT, lambda: self._emit_and_hide(self.add_word_requested)))
        row = self._link_row(actions)
        more = link_button(ALL_ISSUES_TEXT)
        more.clicked.connect(self._open_all)
        row.addWidget(more)
        return row

    def _link_row(self, actions: Sequence[tuple[str, Callable[[], object]]]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(6, 4, 0, 0)
        row.setSpacing(14)
        for label, action in actions:
            button = link_button(label)
            button.clicked.connect(lambda _checked=False, a=action: a())
            row.addWidget(button)
        row.addStretch()
        return row

    def _add_rephrase_header(self) -> None:
        title = self._label(REPHRASE_TEXT)
        title.setObjectName("cardTitle")
        self._layout.addWidget(title)
        if self._sentence:
            sentence = self._label(short_sentence(self._sentence))
            sentence.setObjectName("cardSentence")
            sentence.setWordWrap(True)
            self._layout.addWidget(sentence)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _option_button(self, option: str, sentence: str) -> QPushButton:
        """A button showing the wording with its changes in bold (QPushButton cannot render HTML)."""
        button = _OptionButton(self._frame)
        button.setObjectName("cardFix")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        text = QLabel(changed_words_html(sentence, option), button)
        text.setObjectName("cardOptionText")
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        inner = QVBoxLayout(button)
        inner.setContentsMargins(OPTION_PADDING, OPTION_PADDING, OPTION_PADDING, OPTION_PADDING)
        inner.addWidget(text)
        text.ensurePolished()
        button.clicked.connect(lambda _checked=False, o=option: self._choose_wording(o))
        return button

    def _choose(self, replacement: str) -> None:
        match = self._match
        self.hide()
        if match is not None:
            self.replacement_chosen.emit(match, replacement)

    def _choose_wording(self, option: str) -> None:
        self.hide()
        self.rephrase_chosen.emit(option)

    def _cancel(self) -> None:
        self.hide()
        self.rephrase_cancelled.emit()

    def _emit_and_hide(self, signal: pyqtSignal) -> None:
        match = self._match
        self.hide()
        if match is not None:
            signal.emit(match)

    def _open_all(self) -> None:
        self.hide()
        self.all_issues_requested.emit()


class _OptionButton(QPushButton):
    """A push button as tall as the word-wrapped label inside it (QPushButton sizes by its own text)."""

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.layout().totalHeightForWidth(width)

    def sizeHint(self) -> QSize:
        return QSize(OPTION_BUTTON_WIDTH, self.heightForWidth(OPTION_BUTTON_WIDTH))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


def _clear(layout: QLayout) -> None:
    while (item := layout.takeAt(0)) is not None:
        if item.widget():
            _discard(item.widget())


def _discard(widget: QWidget) -> None:
    """Remove a widget from the card now, so adjustSize() no longer counts it."""
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()
