"""Paste text into the focused app through the clipboard, then restore the user's clipboard.

Every format that is stored as plain memory (text, HTML, RTF, DIB images, file lists, …)
is backed up byte-for-byte. GDI-handle formats such as CF_BITMAP cannot be copied that
way; Windows regenerates bitmaps from CF_DIB, so images still survive.
"""

from __future__ import annotations

import logging
import struct
import threading
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
RESTORE_ATTEMPTS = 3  # each attempt already retries the open OPEN_RETRIES times
RESTORE_RETRY_S = 0.2
# When the field never showed the correction, the user's clipboard goes back only after this
# long: a paste the program is still holding back must not find the user's own clipboard.
UNCONFIRMED_RESTORE_S = 30.0
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


def _put_text(text: str) -> None:
    try:
        with _open_clipboard():
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            _exclude_from_history()
    except pywintypes.error as exc:
        raise ClipboardError(f"The correction could not be put on the clipboard: {exc}") from exc


def paste_text(
    text: str,
    send_keys: Callable[[], None] = send_ctrl_v,
    wait_until_pasted: Callable[[], bool | None] | None = None,
    restore_later: Callable[[ClipboardBackup, int], None] | None = None,
) -> None:
    """Replace the target app's selection with `text`, leaving the clipboard as it was.

    wait_until_pasted returns True once the target shows the paste, or False when it gave up;
    without it a fixed PASTE_SETTLE_S is waited. After False the Ctrl+V may still be waiting in
    the target program (a busy program, or a web page holding it back on purpose), and a paste
    that runs after the restore delivers the user's own clipboard to that program. So the
    correction stays on the clipboard for UNCONFIRMED_RESTORE_S more, and the user's clipboard
    goes back then, unless something else was copied meanwhile.
    """
    backup = backup_clipboard()
    confirmed: bool | None = True
    try:
        _put_text(text)  # empties the clipboard first, so a failure here must still restore it
        sequence = win32clipboard.GetClipboardSequenceNumber()
        send_keys()
        if wait_until_pasted is None:
            time.sleep(PASTE_SETTLE_S)
        else:
            confirmed = wait_until_pasted()
    except BaseException:
        _restore_with_retries(backup)  # nothing was pasted on our account: put it back now
        raise
    if confirmed is False:
        log.warning("Paste not confirmed; the clipboard is restored in %.0f s", UNCONFIRMED_RESTORE_S)
        (restore_later or _restore_later)(backup, sequence)
    else:
        _restore_with_retries(backup)


def _restore_later(backup: ClipboardBackup, sequence: int, delay: float = UNCONFIRMED_RESTORE_S) -> None:
    """Restore after delay, on a timer thread, if the clipboard still holds what we put there."""
    timer = threading.Timer(delay, restore_if_unchanged, (backup, sequence))
    timer.daemon = True  # quitting meanwhile leaves the correction on the clipboard
    timer.start()


def restore_if_unchanged(backup: ClipboardBackup, sequence: int) -> bool:
    """Put the user's clipboard back unless it changed since `sequence` (the user copied
    something else, which must not be overwritten). True when it was restored."""
    if win32clipboard.GetClipboardSequenceNumber() != sequence:
        log.info("The clipboard changed meanwhile; the earlier contents are not put back")
        return False
    _restore_with_retries(backup)
    return True


def _restore_with_retries(backup: ClipboardBackup) -> None:
    """Put the user's clipboard back. A failure is logged, not raised: by now the correction was
    pasted (or an earlier error is already on its way out), so it must not be reported as failed."""
    for attempt in range(1, RESTORE_ATTEMPTS + 1):
        try:
            restore_clipboard(backup)
            return
        except (ClipboardError, pywintypes.error) as exc:
            log.debug("Clipboard restore attempt %d failed: %s", attempt, exc)
            time.sleep(RESTORE_RETRY_S)
    log.warning("Could not restore the clipboard after %d attempts; it still holds the correction",
                RESTORE_ATTEMPTS)
