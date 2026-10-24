"""Tests for proofline.win32_edit against real hidden Win32 edit controls."""

from __future__ import annotations

import ctypes
from collections.abc import Callable, Iterator

import pytest
import pywintypes
import win32api
import win32con
import win32gui

from proofline import win32_edit
from proofline.win32_edit import Win32EditError

SAMPLE = "first line\r\nsecond line"
WM_SETTEXT = 0x000C
HIDDEN_STYLE = win32con.WS_POPUP
EDIT_STYLE = win32con.WS_POPUP | win32con.ES_MULTILINE
RICHEDIT_CLASS = "RICHEDIT50W"
MSFTEDIT_DLL = "Msftedit.dll"

WindowFactory = Callable[[str, int], int]


def _destroy(hwnd: int) -> None:
    try:
        win32gui.DestroyWindow(hwnd)
    except pywintypes.error:
        pass  # already destroyed by the test


@pytest.fixture
def hidden_window() -> Iterator[WindowFactory]:
    """Create hidden top-level windows of any class; destroy them all at teardown."""
    created: list[int] = []

    def create(class_name: str, style: int) -> int:
        hwnd = win32gui.CreateWindowEx(
            0,
            class_name,
            "",
            style,
            0,
            0,
            200,
            100,
            0,
            0,
            win32api.GetModuleHandle(None),
            None,
        )
        created.append(hwnd)
        return hwnd

    yield create
    for hwnd in created:
        _destroy(hwnd)


@pytest.fixture
def edit_hwnd(hidden_window: WindowFactory) -> int:
    return hidden_window("EDIT", EDIT_STYLE)


@pytest.fixture(scope="module")
def richedit_loaded() -> None:
    try:
        ctypes.windll.LoadLibrary(MSFTEDIT_DLL)
    except OSError as exc:
        pytest.skip(f"{MSFTEDIT_DLL} could not be loaded: {exc}")


def _set_text(hwnd: int, text: str) -> None:
    win32gui.SendMessage(hwnd, WM_SETTEXT, 0, text)


def test_is_classic_edit_true_for_edit_control(edit_hwnd: int) -> None:
    assert win32_edit.is_classic_edit(edit_hwnd)


def test_is_classic_edit_false_for_static_window(hidden_window: WindowFactory) -> None:
    static_hwnd = hidden_window("STATIC", HIDDEN_STYLE)
    assert not win32_edit.is_classic_edit(static_hwnd)


def test_is_classic_edit_false_for_invalid_handle() -> None:
    assert not win32_edit.is_classic_edit(0)


def test_window_class_returns_edit(edit_hwnd: int) -> None:
    assert win32_edit.window_class(edit_hwnd).lower() == "edit"


def test_read_text_returns_multiline_text(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, SAMPLE)
    assert win32_edit.read_text(edit_hwnd) == SAMPLE


def test_read_text_empty_control(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, "")
    assert win32_edit.read_text(edit_hwnd) == ""


def test_read_text_truncates_to_max_chars(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, SAMPLE)
    assert win32_edit.read_text(edit_hwnd, max_chars=5) == SAMPLE[:5]


def test_read_text_zero_max_chars_returns_empty(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, SAMPLE)
    assert win32_edit.read_text(edit_hwnd, max_chars=0) == ""


def test_selection_round_trip(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, SAMPLE)
    win32_edit.set_selection(edit_hwnd, 2, 8)
    assert win32_edit.get_selection(edit_hwnd) == (2, 8)


def test_selection_collapsed_caret(edit_hwnd: int) -> None:
    _set_text(edit_hwnd, SAMPLE)
    win32_edit.set_selection(edit_hwnd, 4, 4)
    assert win32_edit.get_selection(edit_hwnd) == (4, 4)


def test_set_selection_rejects_negative_offsets(edit_hwnd: int) -> None:
    with pytest.raises(ValueError):
        win32_edit.set_selection(edit_hwnd, -1, 3)


def test_read_text_rejects_negative_max_chars(edit_hwnd: int) -> None:
    with pytest.raises(ValueError):
        win32_edit.read_text(edit_hwnd, max_chars=-1)


def test_invalid_handle_raises_win32_edit_error() -> None:
    with pytest.raises(Win32EditError):
        win32_edit.read_text(0)
    with pytest.raises(Win32EditError):
        win32_edit.get_selection(0)
    with pytest.raises(Win32EditError):
        win32_edit.set_selection(0, 0, 1)
    with pytest.raises(Win32EditError):
        win32_edit.window_class(0)


def test_destroyed_window_raises_win32_edit_error(hidden_window: WindowFactory) -> None:
    hwnd = hidden_window("EDIT", EDIT_STYLE)
    _destroy(hwnd)
    with pytest.raises(Win32EditError):
        win32_edit.read_text(hwnd)


@pytest.mark.usefixtures("richedit_loaded")
def test_richedit_control_is_classic_edit_and_round_trips(hidden_window: WindowFactory) -> None:
    try:
        hwnd = hidden_window(RICHEDIT_CLASS, EDIT_STYLE)
    except pywintypes.error as exc:
        pytest.skip(f"RichEdit control could not be created: {exc}")
    assert win32_edit.is_classic_edit(hwnd)
    _set_text(hwnd, "rich text")
    assert win32_edit.read_text(hwnd) == "rich text"
    win32_edit.set_selection(hwnd, 0, 4)
    assert win32_edit.get_selection(hwnd) == (0, 4)
