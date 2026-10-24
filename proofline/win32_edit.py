"""Read and select text in classic Win32 edit controls with window messages.

Covers the "Edit" and RichEdit window classes, for apps that lack UI Automation TextPattern.
The system marshals WM_GETTEXT, WM_GETTEXTLENGTH and the EM_*SEL messages across processes
for these standard classes. Every message goes through SendMessageTimeoutW with
SMTO_ABORTIFHUNG, so a hung target fails fast instead of freezing this app.

Limits:
- Offsets are character counts. Classic Edit stores each line break as "\\r\\n", so a break
  counts as two characters. RichEdit uses a single "\\r" per paragraph, so its offsets differ
  from Edit's. Callers map Python string offsets to control offsets themselves.
- EM_GETSEL packs start and end into one DWORD as two 16-bit words. Positions above 65535
  cannot be reported; get_selection truncates them to 16 bits.
- Pointer-based EM_GETSEL / EM_EXGETSEL variants do not marshal cross-process, so this module
  uses the packed return value of EM_GETSEL and never passes pointers with EM_SETSEL.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

CLASSIC_EDIT_CLASSES = ("Edit", "RichEdit20W", "RichEdit20A", "RICHEDIT50W", "RichEdit")
RICHEDIT_CLASS_PREFIX = "richedit"
DEFAULT_MAX_CHARS = 20_000
MESSAGE_TIMEOUT_MS = 500
MAX_CLASS_CHARS = 256
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_GETSEL = 0x00B0
EM_SETSEL = 0x00B1
SMTO_ABORTIFHUNG = 0x0002
WORD_MASK = 0xFFFF
WORD_BITS = 16

_EDIT_CLASSES_LOWER = frozenset(name.lower() for name in CLASSIC_EDIT_CLASSES)

# use_last_error lets us read GetLastError reliably after a failed call.
_user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t

_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetClassNameW.restype = ctypes.c_int
_user32.SendMessageTimeoutW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ULONG_PTR),
)
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM


class Win32EditError(Exception):
    """A window query or message to an edit control failed, timed out, or the handle is invalid."""


def window_class(hwnd: int) -> str:
    """Return the window class name of `hwnd`."""
    buffer = ctypes.create_unicode_buffer(MAX_CLASS_CHARS)
    length = _user32.GetClassNameW(hwnd, buffer, MAX_CLASS_CHARS)
    if length == 0:
        raise Win32EditError(
            f"GetClassNameW failed for hwnd {hwnd:#x} (error {ctypes.get_last_error()})"
        )
    return buffer.value


def is_classic_edit(hwnd: int) -> bool:
    """True when `hwnd` is a classic Edit or RichEdit control. Invalid handles are not edits."""
    try:
        name = window_class(hwnd)
    except Win32EditError as exc:
        log.debug("Not a classic edit: %s", exc)
        return False
    return _is_edit_class_name(name)


def _is_edit_class_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in _EDIT_CLASSES_LOWER or lowered.startswith(RICHEDIT_CLASS_PREFIX)


def _send(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
    """SendMessageTimeoutW with the shared timeout; returns the message result."""
    result = ULONG_PTR(0)
    succeeded = _user32.SendMessageTimeoutW(
        hwnd,
        msg,
        wparam,
        lparam,
        SMTO_ABORTIFHUNG,
        MESSAGE_TIMEOUT_MS,
        ctypes.pointer(result),
    )
    if not succeeded:
        raise Win32EditError(
            f"Message {msg:#x} to hwnd {hwnd:#x} failed or timed out "
            f"(error {ctypes.get_last_error()})"
        )
    return result.value


def read_text(hwnd: int, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Return up to `max_chars` characters of the control's text, with its own line breaks."""
    if max_chars < 0:
        raise ValueError(f"max_chars must be >= 0, got {max_chars}")
    total = _send(hwnd, WM_GETTEXTLENGTH)
    capacity = min(total, max_chars)
    # WM_GETTEXT copies at most wParam-1 characters plus a terminator, so the buffer
    # size also caps how much text crosses the process boundary.
    buffer = ctypes.create_unicode_buffer(capacity + 1)
    _send(hwnd, WM_GETTEXT, capacity + 1, ctypes.addressof(buffer))
    return buffer.value[:max_chars]


def get_selection(hwnd: int) -> tuple[int, int]:
    """Return (start, end) of the selection. Positions are truncated to 16 bits (see module doc)."""
    packed = _send(hwnd, EM_GETSEL)
    start = packed & WORD_MASK
    end = (packed >> WORD_BITS) & WORD_MASK
    return start, end


def set_selection(hwnd: int, start: int, end: int) -> None:
    """Select characters [start, end). Both offsets are control offsets, not Python offsets."""
    if start < 0 or end < 0:
        raise ValueError(f"selection offsets must be >= 0, got {start}, {end}")
    _send(hwnd, EM_SETSEL, start, end)
