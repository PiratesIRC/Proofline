"""The visible page area of a Chromium browser (Edge, Chrome), used to clip a web text box.

UI Automation reports a web text box's full rectangle even when the page has scrolled part of it
behind the browser's tabs and address bar (Edge, measured 2026-11-26: top -160 while the page
area started at y 113), so the badge, placed at the box's visible corner, landed on the toolbar.
Chromium draws each tab's page in a child window of class Chrome_RenderWidgetHostHWND; the
visible one is the area the page shows in. Reading it is a few Win32 calls, no UI Automation.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from proofline.text_snapshot import ScreenRect

log = logging.getLogger(__name__)

CHROMIUM_FRAMEWORK = "Chrome"
PAGE_AREA_CLASS = "Chrome_RenderWidgetHostHWND"
# A box the page edge cuts down to less than this (physical pixels) gets no badge.
MIN_CUT_VISIBLE_PX = 60
MAX_CLASS_CHARS = 256
GA_ROOT = 2

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def clip_to_page(field: ScreenRect, page: ScreenRect) -> ScreenRect | None:
    """The part of field inside page; None when no part of it is (scrolled out of the page)."""
    left, top = max(field.left, page.left), max(field.top, page.top)
    right, bottom = min(field.right, page.right), min(field.bottom, page.bottom)
    if right <= left or bottom <= top:
        return None
    return ScreenRect(left, top, right, bottom)


def page_area(window: int) -> ScreenRect | None:
    """The visible page-area window under window's top-level window; None if there is none."""
    if not window:
        window = _user32.GetForegroundWindow()
    root = _user32.GetAncestor(window, GA_ROOT) or window
    if not root:
        return None
    found: list[ScreenRect] = []

    def visit(hwnd: int, _param: int) -> bool:
        if _class_name(hwnd) == PAGE_AREA_CLASS and _user32.IsWindowVisible(hwnd):
            found.append(_window_rect(hwnd))
        return True

    _user32.EnumChildWindows(root, _ENUM_PROC(visit), 0)
    visible = [r for r in found if r.width > 0 and r.height > 0]
    return max(visible, key=lambda r: r.width * r.height) if visible else None


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(MAX_CLASS_CHARS)
    _user32.GetClassNameW(hwnd, buffer, MAX_CLASS_CHARS)
    return buffer.value


def _window_rect(hwnd: int) -> ScreenRect:
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return ScreenRect(rect.left, rect.top, rect.right, rect.bottom)
