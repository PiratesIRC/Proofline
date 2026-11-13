"""window_response: tell a focused window whose program stopped responding before UIA blocks on it."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from proofline import window_response
from proofline.window_response import ERROR_INVALID_WINDOW_HANDLE, not_responding

OTHER_PID = os.getpid() + 1


def fake_send(answer: int, last_error: int = 0):
    calls = []

    def send(hwnd: int, timeout_ms: int) -> tuple[int, int]:
        calls.append((hwnd, timeout_ms))
        return answer, last_error

    return send, calls


def test_a_window_that_answers_is_responding():
    send, calls = fake_send(1)
    assert not not_responding(10, pid_of=lambda _h: OTHER_PID, send=send)
    assert calls == [(10, window_response.RESPONSE_TIMEOUT_MS)]


def test_no_answer_within_the_limit_is_not_responding():
    send, _ = fake_send(0, last_error=1460)  # ERROR_TIMEOUT
    assert not_responding(10, pid_of=lambda _h: OTHER_PID, send=send)


def test_a_window_closed_meanwhile_is_not_reported_as_hung():
    send, _ = fake_send(0, last_error=ERROR_INVALID_WINDOW_HANDLE)
    assert not not_responding(10, pid_of=lambda _h: OTHER_PID, send=send)


def test_own_windows_are_never_messaged():
    """The monitor thread must not wait on Proofline's own GUI thread."""
    send, calls = fake_send(0)
    assert not not_responding(10, pid_of=lambda _h: os.getpid(), send=send)
    assert calls == []


def test_no_window_is_not_hung():
    send, calls = fake_send(0)
    assert not not_responding(0, pid_of=lambda _h: OTHER_PID, send=send)
    assert calls == []


HUNG_CHILD = r'''
import time
import win32gui
hwnd = win32gui.CreateWindowEx(0, "STATIC", "LTUIAPROBE", 0, 0, 0, 10, 10, 0, 0, 0, None)  # never shown
win32gui.PumpWaitingMessages()
print(hwnd, flush=True)
time.sleep(30)  # stops pumping: the window's thread no longer answers
'''


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 windows")
def test_a_real_window_whose_thread_sleeps_is_reported_within_the_limit():
    child = subprocess.Popen([sys.executable, "-c", HUNG_CHILD], stdout=subprocess.PIPE, text=True)
    try:
        hwnd = int(child.stdout.readline())
        started = time.perf_counter()
        assert not_responding(hwnd)
        assert time.perf_counter() - started < 2.0  # limit 0.25 s; generous for a slow runner
    finally:
        child.kill()
        child.wait()
