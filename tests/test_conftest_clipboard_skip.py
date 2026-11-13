"""The `clipboard` marker skips a test while the Windows session is locked, and only then."""

import ctypes
import sys
import time

import pytest

conftest = sys.modules["conftest"]
ERROR_ACCESS_DENIED = 5


class FakeItem:
    def __init__(self, marked):
        self.marked = marked

    def get_closest_marker(self, name):
        return object() if self.marked and name == "clipboard" else None


def test_clipboard_test_skipped_while_locked(monkeypatch):
    monkeypatch.setattr(conftest, "session_is_locked", lambda: True)
    with pytest.raises(pytest.skip.Exception, match="session is locked"):
        conftest.pytest_runtest_setup(FakeItem(marked=True))


def test_clipboard_test_runs_while_unlocked(monkeypatch):
    monkeypatch.setattr(conftest, "session_is_locked", lambda: False)
    conftest.pytest_runtest_setup(FakeItem(marked=True))


def test_unmarked_test_runs_while_locked(monkeypatch):
    monkeypatch.setattr(conftest, "session_is_locked", lambda: True)
    conftest.pytest_runtest_setup(FakeItem(marked=False))


def _clipboard_open_error() -> int:
    """0 when the clipboard opens (retrying while another program holds it), else the error code."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    error = 0
    for _ in range(20):
        if user32.OpenClipboard(None):
            user32.CloseClipboard()
            return 0
        error = kernel32.GetLastError()
        if error == ERROR_ACCESS_DENIED:
            return error
        time.sleep(0.05)
    return error


def test_session_lock_reading_matches_clipboard_access():
    # The skip exists because a locked session denies every clipboard open (error 5), so the
    # reading must agree with what the clipboard does right now.
    locked = conftest.session_is_locked()
    assert type(locked) is bool
    assert (_clipboard_open_error() == ERROR_ACCESS_DENIED) == locked
