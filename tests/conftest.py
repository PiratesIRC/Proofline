import ctypes
import ctypes.wintypes as wt
import functools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WTS_SESSION_INFO_EX = 25  # WTS_INFO_CLASS.WTSSessionInfoEx
WTS_SESSIONSTATE_LOCK = 0


class _WtsInfoExLevel1(ctypes.Structure):
    _fields_ = [
        ("SessionId", wt.ULONG), ("SessionState", ctypes.c_int), ("SessionFlags", wt.LONG),
        ("WinStationName", wt.WCHAR * 33), ("UserName", wt.WCHAR * 21), ("DomainName", wt.WCHAR * 18),
        ("LogonTime", ctypes.c_longlong), ("ConnectTime", ctypes.c_longlong),
        ("DisconnectTime", ctypes.c_longlong), ("LastInputTime", ctypes.c_longlong),
        ("CurrentTime", ctypes.c_longlong),
    ]


class _WtsInfoEx(ctypes.Structure):
    _fields_ = [("Level", wt.DWORD), ("Data", _WtsInfoExLevel1)]


@functools.cache
def session_is_locked() -> bool:
    """True when Windows reports this session as locked; False when unlocked or unknown.

    While the session is locked every clipboard open fails with "Access is denied" (error 5),
    for every process (measured 2026-10-29; the same tests passed after unlocking, 2026-10-31).
    """
    kernel32, wtsapi = ctypes.windll.kernel32, ctypes.windll.wtsapi32
    session = wt.DWORD()
    if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session)):
        return False
    buf, size = ctypes.c_void_p(), wt.DWORD()
    if not wtsapi.WTSQuerySessionInformationW(None, session.value, WTS_SESSION_INFO_EX,
                                              ctypes.byref(buf), ctypes.byref(size)):
        return False
    try:
        info = ctypes.cast(buf, ctypes.POINTER(_WtsInfoEx)).contents
        return info.Level == 1 and info.Data.SessionFlags == WTS_SESSIONSTATE_LOCK
    finally:
        wtsapi.WTSFreeMemory(buf)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Before fixtures run, so the clipboard save/restore fixture never touches a locked clipboard.
    if item.get_closest_marker("clipboard") and session_is_locked():
        pytest.skip("the Windows session is locked, so the clipboard cannot be opened")
