"""Click-through window over the focused field that draws a wavy line under each flagged word."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PyQt6.QtCore import QPointF, QRect
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

from proofline.non_activating import make_non_activating

UNDERLINE_COLOR = QColor(229, 40, 60)
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

    @property
    def rects(self) -> tuple[QRect, ...]:
        """The word rectangles drawn, relative to the window."""
        return self._rects

    def show_underlines(self, field: QRect, words: Sequence[QRect]) -> None:
        """Underline words (logical screen coordinates) inside the field's rectangle."""
        self._rects = tuple(word.translated(-field.topLeft()) for word in words)
        self.setGeometry(field)
        self.update()
        if not self.isVisible():
            self.show()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(UNDERLINE_COLOR, LINE_WIDTH))
        for rect in self._rects:
            painter.drawPath(wave_path(rect))
