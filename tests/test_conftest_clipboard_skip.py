"""The `clipboard` marker skips a test while the Windows session is locked, and only then."""

import sys

import pytest

conftest = sys.modules["conftest"]


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


def test_session_is_locked_reads_a_boolean():
    assert conftest.session_is_locked() in (True, False)
