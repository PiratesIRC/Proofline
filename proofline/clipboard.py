"""Paste text into the focused app through the clipboard, then restore the user's clipboard.

Every format that is stored as plain memory (text, HTML, RTF, DIB images, file lists, …)
is backed up byte-for-byte. GDI-handle formats such as CF_BITMAP cannot be copied that
way; Windows regenerates bitmaps from CF_DIB, so images still survive.
"""

from __future__ import annotations

import logging
import struct
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pywintypes
import win32api
import win32clipboard
import win32con
import win32gui

log = logging.getLogger(__name__)

OPEN_RETRIES = 10
OPEN_RETRY_DELAY_S = 0.02
PASTE_SETTLE_S = 0.3  # time the target app needs to read the clipboard after Ctrl+V
VK_CONTROL = 0x11
VK_V = 0x56
VK_DELETE = 0x2E
GDI_HANDLE_FORMATS = frozenset(
    {
        win32con.CF_BITMAP,
        win32con.CF_METAFILEPICT,
        win32con.CF_PALETTE,
        win32con.CF_ENHMETAFILE,
        win32con.CF_OWNERDISPLAY,
        win32con.CF_DSPBITMAP,
        win32con.CF_DSPMETAFILEPICT,
        win32con.CF_DSPENHMETAFILE,
    }
)
# Registered formats that keep our temporary content out of Win+V history and cloud sync.
_DWORD_ZERO = struct.pack("<I", 0)
HISTORY_EXCLUSION_FORMATS = (
    ("ExcludeClipboardContentFromMonitorProcessing", b"\0"),
    ("CanIncludeInClipboardHistory", _DWORD_ZERO),
    ("CanUploadToCloudClipboard", _DWORD_ZERO),
)

ClipboardBackup = tuple[tuple[int, bytes], ...]


class ClipboardError(Exception):
    """The clipboard could not be opened or written."""


@contextmanager
def _owner_window() -> Iterator[int]:
    """A hidden message-only window that owns the clipboard for one open, then is destroyed.

    Opening with no window (OpenClipboard(None)) lost the clipboard right after a write in
    about 1 open in 30 on 2026-10-31 (error 1418); with an owner window it never did. The
    window does not outlive the open: the monitor thread pumps no messages, and Windows
    sends the clipboard owner WM_DESTROYCLIPBOARD whenever another app copies.
    """
    hwnd = win32gui.CreateWindow("STATIC", "Proofline clipboard", 0, 0, 0, 0, 0,
                                 win32con.HWND_MESSAGE, 0, 0, None)
    try:
        yield hwnd
    finally:
        win32gui.DestroyWindow(hwnd)


@contextmanager
def _open_clipboard() -> Iterator[None]:
    with _owner_window() as owner:
        last_error: Exception | None = None
        for _ in range(OPEN_RETRIES):
            try:
                win32clipboard.OpenClipboard(owner)
                break
            except pywintypes.error as exc:  # another app is holding the clipboard
                last_error = exc
                time.sleep(OPEN_RETRY_DELAY_S)
        else:
            raise ClipboardError(f"The clipboard is busy: {last_error}")
        try:
            yield
        finally:
            win32clipboard.CloseClipboard()


def backup_clipboard() -> ClipboardBackup:
    items: list[tuple[int, bytes]] = []
    skipped: list[int] = []
    with _open_clipboard():
        fmt = win32clipboard.EnumClipboardFormats(0)
        while fmt:
            if fmt in GDI_HANDLE_FORMATS:
                skipped.append(fmt)
            else:
                try:
                    handle = win32clipboard.GetClipboardDataHandle(fmt)
                    items.append((fmt, win32clipboard.GetGlobalMemory(handle)))
                except pywintypes.error:
                    skipped.append(fmt)
            fmt = win32clipboard.EnumClipboardFormats(fmt)
    log.debug("Clipboard backup: %d format(s) saved, skipped %s", len(items), skipped)
    return tuple(items)


def restore_clipboard(backup: ClipboardBackup) -> None:
    with _open_clipboard():
        win32clipboard.EmptyClipboard()
        for fmt, data in backup:
            try:
                win32clipboard.SetClipboardData(fmt, data)
            except pywintypes.error as exc:
                log.warning("Could not restore clipboard format %d: %s", fmt, exc)
        _exclude_from_history(already_set={fmt for fmt, _ in backup})
    log.debug("Clipboard restored (%d format(s))", len(backup))


def _exclude_from_history(already_set: set[int] = frozenset()) -> None:
    for name, value in HISTORY_EXCLUSION_FORMATS:
        fmt = win32clipboard.RegisterClipboardFormat(name)
        if fmt not in already_set:
            win32clipboard.SetClipboardData(fmt, value)


def send_ctrl_v() -> None:
    win32api.keybd_event(VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(VK_V, 0, 0, 0)
    win32api.keybd_event(VK_V, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def send_delete() -> None:
    win32api.keybd_event(VK_DELETE, 0, 0, 0)
    win32api.keybd_event(VK_DELETE, 0, win32con.KEYEVENTF_KEYUP, 0)


def paste_text(text: str, send_keys: Callable[[], None] = send_ctrl_v) -> None:
    """Replace the target app's selection with `text`, leaving the clipboard as it was."""
    backup = backup_clipboard()
    with _open_clipboard():
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        _exclude_from_history()
    try:
        send_keys()
        time.sleep(PASTE_SETTLE_S)
    finally:
        restore_clipboard(backup)
