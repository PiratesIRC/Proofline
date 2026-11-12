"""Failure paths of paste_text, with the Windows clipboard calls replaced by fakes.

These run without the real clipboard (and so also while the session is locked)."""

from contextlib import nullcontext

import pytest
import pywintypes

from proofline import clipboard
from proofline.clipboard import ClipboardError, paste_text

BACKUP = ((13, b"u\x00s\x00e\x00r\x00\x00\x00"),)


@pytest.fixture
def fake_clipboard(monkeypatch):
    """Records restores; the correction write fails with a pywin32 error."""
    restored = []
    monkeypatch.setattr(clipboard, "PASTE_SETTLE_S", 0)
    monkeypatch.setattr(clipboard, "backup_clipboard", lambda: BACKUP)
    monkeypatch.setattr(clipboard, "restore_clipboard", restored.append)
    monkeypatch.setattr(clipboard, "_open_clipboard", nullcontext)
    monkeypatch.setattr(clipboard.win32clipboard, "EmptyClipboard", lambda: None)

    def failing_set(fmt, data):
        raise pywintypes.error(1418, "SetClipboardData", "Thread does not have a clipboard open.")

    monkeypatch.setattr(clipboard.win32clipboard, "SetClipboardData", failing_set)
    return restored


def test_a_failed_write_restores_the_clipboard_and_sends_no_keys(fake_clipboard):
    sent = []
    with pytest.raises(ClipboardError):
        paste_text("correction", send_keys=lambda: sent.append("ctrl+v"))
    assert fake_clipboard == [BACKUP]
    assert sent == []


@pytest.fixture
def restore_fails(monkeypatch):
    """The correction write and keys succeed; the restore fails `failures` times, then works."""
    calls = []
    state = {"failures": 99}
    monkeypatch.setattr(clipboard, "PASTE_SETTLE_S", 0)
    monkeypatch.setattr(clipboard, "RESTORE_RETRY_S", 0)
    monkeypatch.setattr(clipboard, "backup_clipboard", lambda: BACKUP)
    monkeypatch.setattr(clipboard, "_put_text", lambda text: None)

    def restore(backup):
        calls.append(backup)
        if len(calls) <= state["failures"]:
            raise ClipboardError("The clipboard is busy")

    monkeypatch.setattr(clipboard, "restore_clipboard", restore)
    return calls, state


def test_a_failed_restore_after_a_good_paste_does_not_fail_the_correction(restore_fails, caplog):
    calls, _state = restore_fails
    paste_text("correction", send_keys=lambda: None)  # no exception: the correction was pasted
    assert len(calls) == clipboard.RESTORE_ATTEMPTS
    assert "Could not restore the clipboard" in caplog.text


def test_a_busy_clipboard_is_restored_on_a_later_attempt(restore_fails):
    calls, state = restore_fails
    state["failures"] = 1
    paste_text("correction", send_keys=lambda: None)
    assert len(calls) == 2
