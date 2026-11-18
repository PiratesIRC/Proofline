"""Mouse events for dragging the badge in tests (global positions are what the badge reads)."""

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton


def _event(kind, widget, global_pos: QPoint, button, buttons):
    local = QPointF(widget.mapFromGlobal(global_pos))
    return QMouseEvent(kind, local, QPointF(global_pos), button, buttons, Qt.KeyboardModifier.NoModifier)


def press(widget, global_pos: QPoint, button=LEFT) -> None:
    widget.mousePressEvent(_event(QEvent.Type.MouseButtonPress, widget, global_pos, button, button))


def move(widget, global_pos: QPoint, held=LEFT) -> None:
    widget.mouseMoveEvent(_event(QEvent.Type.MouseMove, widget, global_pos, Qt.MouseButton.NoButton, held))


def release(widget, global_pos: QPoint, button=LEFT) -> None:
    widget.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, widget, global_pos, button, Qt.MouseButton.NoButton))


def drag(widget, start: QPoint, end: QPoint, button=LEFT) -> None:
    press(widget, start, button)
    move(widget, end, button)
    release(widget, end, button)
