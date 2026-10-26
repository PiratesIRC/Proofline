"""Click-through window over the focused field that draws a wavy line under each flagged word."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PyQt6.QtCore import QPointF, QRect
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

from proofline.non_activating import make_non_activating

UNDERLINE_COLOR = QColor(229, 40, 60)
AI_UNDERLINE_COLOR = QColor(142, 68, 173)  # AI findings, apart from LanguageTool's
LINE_WIDTH = 1.6
WAVE_PERIOD = 6.0  # logical px per full wave
WAVE_AMPLITUDE = 1.5


def wave_path(rect: QRect) -> QPainterPath:
    """A sine wave along the bottom edge of rect, kept inside it."""
    baseline = rect.bottom() - WAVE_AMPLITUDE
    path = QPainterPath(QPointF(rect.left(), baseline))
    for x in range(rect.left() + 1, rect.right() + 2):
        phase = 2 * math.pi * (x - rect.left()) / WAVE_PERIOD
        path.lineTo(QPointF(x, baseline + WAVE_AMPLITUDE * math.sin(phase)))
    return path


class UnderlineOverlay(QWidget):
    """Covers the field; mouse input goes straight through to the app underneath."""

    def __init__(self) -> None:
        super().__init__()
        make_non_activating(self, click_through=True)
        self._rects: tuple[QRect, ...] = ()
        self._ai_flags: tuple[bool, ...] = ()

    @property
    def rects(self) -> tuple[QRect, ...]:
        """The word rectangles drawn, relative to the window."""
        return self._rects

    @property
    def ai_flags(self) -> tuple[bool, ...]:
        """Per word rectangle: drawn in the AI colour."""
        return self._ai_flags

    def show_underlines(self, field: QRect, words: Sequence[QRect], ai_flags: Sequence[bool] = ()) -> None:
        """Underline words (logical screen coordinates) inside the field's rectangle.

        ai_flags has one entry per word rectangle; a True one is drawn in AI_UNDERLINE_COLOR.
        """
        self._rects = tuple(word.translated(-field.topLeft()) for word in words)
        self._ai_flags = tuple(ai_flags)
        self.setGeometry(field)
        self.update()
        if not self.isVisible():
            self.show()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index, rect in enumerate(self._rects):
            ai = index < len(self._ai_flags) and self._ai_flags[index]
            painter.setPen(QPen(AI_UNDERLINE_COLOR if ai else UNDERLINE_COLOR, LINE_WIDTH))
            painter.drawPath(wave_path(rect))
