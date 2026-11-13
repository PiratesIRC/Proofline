"""Tell whether the focused window's program still answers, before UI Automation waits on it.

Measured 2026-11-13: one UIA read of a classic Win32 edit whose program had stopped responding
blocked for 59.5 s, until that program ended; the `uiautomation` package's client object has no
call time limit. An empty message (WM_NULL) with a 250 ms limit answers in under 1 ms from a
working window and fails after the limit from a stopped one. The monitor skips that poll.

Plain Win32 calls, no UIA: safe to import anywhere, called on the monitor thread.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from ctypes import wintypes

RESPONSE_TIMEOUT_MS = 250
WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
ERROR_INVALID_WINDOW_HANDLE = 1400

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
_user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT),
    ]


def _send_null(hwnd: int, timeout_ms: int) -> tuple[int, int]:
    """SendMessageTimeoutW(WM_NULL): (its return value, the last error when it returned 0)."""
    result = ctypes.c_size_t()
    answer = _user32.SendMessageTimeoutW(hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result))
    return answer, (0 if answer else ctypes.get_last_error())


def _pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def focused_window() -> int:
    """The window with keyboard focus in the foreground program, else the foreground window; 0 for none."""
    foreground = _user32.GetForegroundWindow() or 0
    if not foreground:
        return 0
    info = _GuiThreadInfo(cbSize=ctypes.sizeof(_GuiThreadInfo))
    thread = _user32.GetWindowThreadProcessId(foreground, None)
    if thread and _user32.GetGUIThreadInfo(thread, ctypes.byref(info)) and info.hwndFocus:
        return info.hwndFocus
    return foreground


def not_responding(
    hwnd: int,
    pid_of: Callable[[int], int] = _pid_of,
    send: Callable[[int, int], tuple[int, int]] = _send_null,
) -> bool:
    """True when hwnd's thread does not answer within RESPONSE_TIMEOUT_MS.

    Proofline's own windows are never messaged: the monitor thread must not wait on the GUI
    thread. A window that closed meanwhile is not reported (the next poll sees the new focus).
    """
    if not hwnd or pid_of(hwnd) == os.getpid():
        return False
    answer, last_error = send(hwnd, RESPONSE_TIMEOUT_MS)
    return not answer and last_error != ERROR_INVALID_WINDOW_HANDLE
