"""The floating badge: a small status circle that stays legible on light and dark
fields and animates just enough to be noticed.

Look: a mid-tone coloured disc with a white ring and a thin dark outline plus a soft
shadow, so it separates from white fields (outline/shadow) and black fields (ring).

Motion (skipped when Windows "Animation effects" is off):
- CHECKING: a white arc spins inside the disc.
- ISSUES: the disc pops, then a soft ring pulses outward a few times and stops.
- CLEAN: a single pop.
The repaint timer only runs while something is moving.
"""

from __future__ import annotations

import ctypes
import enum
import math
import time
from collections.abc import Callable

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from proofline.non_activating import make_non_activating

BADGE_SIZE = 36  # widget size; leaves room around the disc for the pulse ring
DISC_DIAMETER = 24  # WCAG 2.2 target size (2.5.8) asks for at least 24 px
RING_PX = 2.0
OUTLINE = QColor(0, 0, 0, 120)
SHADOW = QColor(0, 0, 0, 55)
FONT_PX = 13
MAX_SHOWN_COUNT = 9

FRAME_MS = 33  # ~30 fps while animating
SPIN_PERIOD_MS = 900
SPIN_SPAN_DEG = 110
POP_MS = 260
POP_SCALE = 0.18
PULSE_PERIOD_MS = 1100
ATTENTION_PULSES = 3
PULSE_MAX_ALPHA = 170
PULSE_WHITE_RATIO = 0.8
MS_PER_S = 1000
SPI_GETCLIENTAREAANIMATION = 0x1042


class BadgeState(enum.Enum):
    CHECKING = ("#757575", "…", "Checking…")
    CLEAN = ("#2e7d32", "✓", "No issues found")
    ISSUES = ("#d32f2f", "", "Click to see issues")
    ERROR = ("#5d4037", "!", "LanguageTool server problem")

    def __init__(self, color: str, symbol: str, tooltip: str) -> None:
        self.color = color
        self.symbol = symbol
        self.tooltip = tooltip


def system_animations_enabled() -> bool:
    """Windows Settings > Accessibility > Visual effects > Animation effects."""
    enabled = ctypes.c_bool(True)
    ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
    return bool(enabled.value) if ok else True


def animation_duration_ms(state: BadgeState) -> float:
    """How long a state animates after it begins; infinity for the spinner."""
    if state is BadgeState.CHECKING:
        return math.inf
    if state is BadgeState.ISSUES:
        return ATTENTION_PULSES * PULSE_PERIOD_MS
    if state is BadgeState.CLEAN:
        return POP_MS
    return 0


def pop_scale(elapsed_ms: float) -> float:
    """1.0 → 1+POP_SCALE → 1.0 over POP_MS."""
    if elapsed_ms >= POP_MS:
        return 1.0
    return 1.0 + POP_SCALE * math.sin(math.pi * elapsed_ms / POP_MS)


def accessible_name(state: BadgeState, count: int) -> str:
    """What a screen reader announces for the badge."""
    if state is BadgeState.ISSUES:
        return f"Proofline: {count} issue{'' if count == 1 else 's'}. Click to see them."
    return f"Proofline: {state.tooltip[:1].lower()}{state.tooltip[1:]}"


def badge_label(state: BadgeState, count: int) -> str:
    if state is BadgeState.ISSUES:
        return str(count) if count <= MAX_SHOWN_COUNT else f"{MAX_SHOWN_COUNT}+"
    return state.symbol


class BadgeWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(
        self,
        animations_enabled: Callable[[], bool] = system_animations_enabled,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        make_non_activating(self)
        self.setFixedSize(BADGE_SIZE, BADGE_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._animations_enabled = animations_enabled
        self._clock = clock
        self._state = BadgeState.CHECKING
        self._count = 0
        self._since = clock()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._on_frame)

    @property
    def state(self) -> BadgeState:
        return self._state

    @property
    def is_animating(self) -> bool:
        return self._timer.isActive()

    def set_state(self, state: BadgeState, count: int = 0, tooltip: str = "") -> None:
        if (state, count) != (self._state, self._count):
            self._since = self._clock()  # a new state or count replays its animation
        self._state = state
        self._count = count
        self.setToolTip(tooltip or state.tooltip)
        self.setAccessibleName(accessible_name(state, count))
        self._sync_timer()
        self.update()

    def elapsed_ms(self) -> float:
        return (self._clock() - self._since) * MS_PER_S

    def _wants_animation(self) -> bool:
        return self._animations_enabled() and self.elapsed_ms() < animation_duration_ms(self._state)

    def _sync_timer(self) -> None:
        if self._wants_animation() and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()

    def _on_frame(self) -> None:
        if not self._wants_animation():
            self._timer.stop()
        self.update()

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event: object) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def paintEvent(self, _event: QPaintEvent) -> None:
        animate = self._animations_enabled()
        elapsed = self.elapsed_ms() if animate else math.inf
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = BADGE_SIZE / 2
        if self._state is BadgeState.ISSUES and elapsed < animation_duration_ms(self._state):
            _draw_pulse(painter, centre, self._state.color, elapsed)
        scale = pop_scale(elapsed) if self._state in (BadgeState.ISSUES, BadgeState.CLEAN) else 1.0
        radius = DISC_DIAMETER / 2 * scale
        _draw_disc(painter, centre, radius, self._state.color)
        if self._state is BadgeState.CHECKING and animate:
            _draw_spinner(painter, centre, radius, elapsed)
        elif self._state is BadgeState.CLEAN:
            _draw_checkmark(painter, centre, radius)
        else:
            _draw_label(painter, badge_label(self._state, self._count))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _draw_pulse(painter: QPainter, centre: float, color: str, elapsed: float) -> None:
    progress = (elapsed % PULSE_PERIOD_MS) / PULSE_PERIOD_MS
    inner = DISC_DIAMETER / 2
    radius = inner + progress * (BADGE_SIZE / 2 - inner - 1)
    alpha = int(PULSE_MAX_ALPHA * (1 - progress))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Coloured ring shows on light fields; the faint white ring just outside it shows on dark ones.
    halo = QColor("white")
    halo.setAlpha(int(alpha * PULSE_WHITE_RATIO))
    painter.setPen(QPen(halo, 1.5))
    painter.drawEllipse(QRectF(centre - radius - 1.5, centre - radius - 1.5, 2 * radius + 3, 2 * radius + 3))
    ring = QColor(color)
    ring.setAlpha(alpha)
    painter.setPen(QPen(ring, 2))
    painter.drawEllipse(QRectF(centre - radius, centre - radius, 2 * radius, 2 * radius))


def _draw_disc(painter: QPainter, centre: float, radius: float, color: str) -> None:
    def circle(r: float, dy: float = 0) -> QRectF:
        return QRectF(centre - r, centre - r + dy, 2 * r, 2 * r)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SHADOW)
    painter.drawEllipse(circle(radius + RING_PX, dy=1))  # soft drop shadow
    painter.setBrush(QColor(color))
    painter.setPen(QPen(QColor("white"), RING_PX))
    painter.drawEllipse(circle(radius))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(OUTLINE, 1))
    painter.drawEllipse(circle(radius + RING_PX / 2 + 0.5))  # thin dark edge for white fields


def _draw_spinner(painter: QPainter, centre: float, radius: float, elapsed: float) -> None:
    inset = radius * 0.45
    angle = -360 * (elapsed % SPIN_PERIOD_MS) / SPIN_PERIOD_MS
    pen = QPen(QColor("white"), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    rect = QRectF(centre - inset, centre - inset, 2 * inset, 2 * inset)
    painter.drawArc(rect, int(angle * 16), SPIN_SPAN_DEG * 16)


def _draw_checkmark(painter: QPainter, centre: float, radius: float) -> None:
    """Drawn as a path: the ✓ glyph renders unevenly at this size."""
    unit = radius * 0.5
    path = QPainterPath()
    path.moveTo(centre - unit, centre)
    path.lineTo(centre - unit * 0.25, centre + unit * 0.7)
    path.lineTo(centre + unit, centre - unit * 0.6)
    pen = QPen(QColor("white"), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _draw_label(painter: QPainter, label: str) -> None:
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(FONT_PX)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(QRectF(0, 0, BADGE_SIZE, BADGE_SIZE), Qt.AlignmentFlag.AlignCenter, label)
