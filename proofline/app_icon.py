"""Draws the app icon: a rounded square in the chosen colour with a white letter.

Nothing is loaded from disk. Each size is drawn on its own (not scaled from one large
image), so the 16 px tray icon stays sharp. An optional dot in the top right corner
marks "an update is waiting".
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ICON_TEXT = "P"
TEXT_COLOR = "white"
DOT_COLOR = "#29b6f6"
FONT_FAMILY = "Segoe UI"
MARGIN_DIVISOR = 32  # no margin below 32 px, so small tray icons use every pixel
CORNER_RATIO = 0.24  # corner radius as a share of the square's side
SHADE_START = 0.58  # the lower part darkens from here down; above it the colour is exact
SHADE_ALPHA = 60
FONT_RATIO = 0.64  # letter height as a share of the icon size
UNDERLINE_MIN_SIZE = 32  # below this the letter stands alone; a line under it would blur
UNDERLINE_FONT_RATIO = 0.56
UNDERLINE_Y = 0.80  # the wavy line's centre, as a share of the icon size
UNDERLINE_SPAN = (0.27, 0.73)
UNDERLINE_WAVES = 3
UNDERLINE_HEIGHT = 0.035  # wave amplitude
UNDERLINE_WIDTH = 0.055  # pen width
LETTER_LIFT = 0.07  # the letter moves up this much to make room for the line
DOT_RATIO = 0.36  # the dot's diameter
DOT_GAP_RATIO = 0.06  # the transparent ring between the dot and the square


def make_icon(color: str, text: str = ICON_TEXT, dot: bool = False, text_color: str = TEXT_COLOR) -> QIcon:
    """The icon in every size Windows asks for (tray, taskbar, Alt+Tab, notifications)."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(draw_icon(size, color, text, dot, text_color))
    return icon


def draw_icon(size: int, color: str, text: str = ICON_TEXT, dot: bool = False,
              text_color: str = TEXT_COLOR) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _draw_square(painter, size, QColor(color))
    underlined = text == ICON_TEXT and size >= UNDERLINE_MIN_SIZE
    _draw_text(painter, size, text, QColor(text_color), underlined)
    if underlined:
        _draw_underline(painter, size, QColor(text_color))
    if dot:
        _draw_dot(painter, size)
    painter.end()
    return pixmap


def _draw_square(painter: QPainter, size: int, color: QColor) -> None:
    margin = size // MARGIN_DIVISOR
    side = size - 2 * margin
    square = QPainterPath()
    square.addRoundedRect(QRectF(margin, margin, side, side), side * CORNER_RATIO, side * CORNER_RATIO)
    painter.fillPath(square, color)
    shade = QLinearGradient(0, size * SHADE_START, 0, size)
    shade.setColorAt(0, QColor(0, 0, 0, 0))
    shade.setColorAt(1, QColor(0, 0, 0, SHADE_ALPHA))
    painter.fillPath(square, shade)


def _draw_text(painter: QPainter, size: int, text: str, color: QColor, underlined: bool) -> None:
    font = QFont(FONT_FAMILY)
    font.setBold(True)
    font.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)  # no colour fringes in a saved image
    # pixels, so it fits regardless of screen DPI
    font.setPixelSize(max(1, round(size * (UNDERLINE_FONT_RATIO if underlined else FONT_RATIO))))
    painter.setFont(font)
    painter.setPen(color)
    lift = size * LETTER_LIFT if underlined else 0
    painter.drawText(QRectF(0, -lift, size, size), Qt.AlignmentFlag.AlignCenter, text)


def _draw_underline(painter: QPainter, size: int, color: QColor) -> None:
    """The wavy line Proofline draws under a flagged word."""
    left, right = (size * share for share in UNDERLINE_SPAN)
    y, height = size * UNDERLINE_Y, size * UNDERLINE_HEIGHT
    half_wave = (right - left) / (UNDERLINE_WAVES * 2)
    wave = QPainterPath(QPointF(left, y))
    for index in range(UNDERLINE_WAVES * 2):
        start = left + index * half_wave
        peak = y - height * 2 if index % 2 == 0 else y + height * 2
        wave.quadTo(QPointF(start + half_wave / 2, peak), QPointF(start + half_wave, y))
    pen = QPen(color, size * UNDERLINE_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.strokePath(wave, pen)


def _draw_dot(painter: QPainter, size: int) -> None:
    """A dot in the top right corner, with a transparent ring so it reads on any icon colour."""
    diameter = size * DOT_RATIO
    gap = size * DOT_GAP_RATIO
    centre = QPointF(size - diameter / 2, diameter / 2)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.setBrush(QColor("black"))
    painter.drawEllipse(centre, diameter / 2 + gap, diameter / 2 + gap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setBrush(QColor(DOT_COLOR))
    painter.drawEllipse(centre, diameter / 2, diameter / 2)
