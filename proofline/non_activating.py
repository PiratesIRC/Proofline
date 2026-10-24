"""Window setup shared by the badge and the popup: frameless, topmost, translucent,
and never activated, so the text field the user is typing in keeps focus."""

from __future__ import annotations

import ctypes

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def make_non_activating(widget: QWidget) -> None:
    """Frameless, topmost, no taskbar entry, and never activated by clicks."""
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Tool
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    # Must be set before winId() creates the native window, or Windows never makes
    # it layered and the transparent areas render black.
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    hwnd = int(widget.winId())
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
