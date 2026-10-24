"""These use the real Windows clipboard; the user's clipboard is saved and restored."""

import pytest
import win32clipboard
import win32con

from proofline import clipboard
from proofline.clipboard import backup_clipboard, paste_text, restore_clipboard

CUSTOM_FORMAT_NAME = "ProoflineTestFormat"


@pytest.fixture(autouse=True)
def preserve_user_clipboard(monkeypatch):
    monkeypatch.setattr(clipboard, "PASTE_SETTLE_S", 0)
    saved = backup_clipboard()
    yield
    restore_clipboard(saved)


def set_clipboard(text, custom=None):
    # Retrying open: clipboard-history tools briefly hold the clipboard after each change.
    with clipboard._open_clipboard():
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        if custom is not None:
            fmt = win32clipboard.RegisterClipboardFormat(CUSTOM_FORMAT_NAME)
            win32clipboard.SetClipboardData(fmt, custom)


def read_clipboard():
    with clipboard._open_clipboard():
        text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        fmt = win32clipboard.RegisterClipboardFormat(CUSTOM_FORMAT_NAME)
        custom = win32clipboard.GetClipboardData(fmt) if win32clipboard.IsClipboardFormatAvailable(fmt) else None
        return text, custom


def test_backup_and_restore_round_trip_text_and_custom_format():
    set_clipboard("original ✓ text", custom=b"\x01\x02binary")
    saved = backup_clipboard()
    set_clipboard("something else")
    restore_clipboard(saved)
    assert read_clipboard() == ("original ✓ text", b"\x01\x02binary")


def test_paste_puts_correction_on_clipboard_during_keystroke_then_restores():
    set_clipboard("user data", custom=b"keep me")
    seen_during_paste = []
    paste_text("is", send_keys=lambda: seen_during_paste.append(read_clipboard()[0]))
    assert seen_during_paste == ["is"]
    assert read_clipboard() == ("user data", b"keep me")


def test_paste_restores_clipboard_even_if_keystroke_fails():
    set_clipboard("user data")

    def fail():
        raise OSError("SendInput failed")

    with pytest.raises(OSError):
        paste_text("is", send_keys=fail)
    assert read_clipboard()[0] == "user data"
