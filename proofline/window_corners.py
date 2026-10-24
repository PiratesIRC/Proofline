"""Ask Windows 11 to draw a window with rounded corners, a border and a drop shadow.

DWM only rounds windows that are not translucent (layered), so a widget using this must
paint an opaque background. Windows 10 ignores the request and keeps square corners.
"""

from __future__ import annotations

import ctypes
import logging

from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
S_OK = 0


def round_corners(widget: QWidget) -> bool:
    """Request rounded corners for the widget's native window; True if Windows accepted."""
    preference = ctypes.c_int(DWMWCP_ROUND)
    try:
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(widget.winId()),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except (AttributeError, OSError) as exc:
        log.debug("Rounded corners unavailable: %s", exc)
        return False
    if result != S_OK:
        log.debug("Rounded corners not supported (HRESULT %#x)", result & 0xFFFFFFFF)
    return result == S_OK
