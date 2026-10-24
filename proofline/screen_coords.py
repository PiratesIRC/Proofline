"""Convert physical screen pixels (what UI Automation reports) to Qt logical coordinates.

Qt scales each screen around its own top-left corner, so a physical point p on a
screen with origin o and scale factor s maps to o + (p - o) / s.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QGuiApplication

from proofline.text_snapshot import ScreenRect


@dataclass(frozen=True)
class ScreenInfo:
    """Logical geometry, available (non-taskbar) geometry, and scale factor of a screen."""

    geometry: QRect
    available: QRect
    scale: float

    def native_contains(self, x: int, y: int) -> bool:
        left, top = self.geometry.x(), self.geometry.y()
        right = left + self.geometry.width() * self.scale
        bottom = top + self.geometry.height() * self.scale
        return left <= x < right and top <= y < bottom

    def to_logical(self, x: int, y: int) -> QPoint:
        left, top = self.geometry.x(), self.geometry.y()
        return QPoint(left + round((x - left) / self.scale), top + round((y - top) / self.scale))


def current_screens() -> tuple[ScreenInfo, ...]:
    return tuple(
        ScreenInfo(s.geometry(), s.availableGeometry(), s.devicePixelRatio())
        for s in QGuiApplication.screens()
    )


def screen_for(x: int, y: int, screens: Sequence[ScreenInfo]) -> ScreenInfo | None:
    return next((s for s in screens if s.native_contains(x, y)), screens[0] if screens else None)


def to_logical_rect(rect: ScreenRect, screens: Sequence[ScreenInfo]) -> QRect:
    """Map a physical rect using the scale of the screen holding its top-left corner."""
    screen = screen_for(rect.left, rect.top, screens)
    if screen is None:
        return QRect(rect.left, rect.top, rect.width, rect.height)
    top_left = screen.to_logical(rect.left, rect.top)
    bottom_right = screen.to_logical(rect.right, rect.bottom)
    return QRect(top_left.x(), top_left.y(), bottom_right.x() - top_left.x(), bottom_right.y() - top_left.y())
