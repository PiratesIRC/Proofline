"""Win32 fallback for selecting text in classic Edit controls (real hidden Edit window)."""

import pytest
import win32con
import win32gui

from proofline import text_replace, win32_edit
from proofline.replace_request import ReplaceError, ReplaceRequest

TEXT = "This are a test."


@pytest.fixture
def edit_hwnd():
    hwnd = win32gui.CreateWindowEx(0, "EDIT", "", win32con.WS_OVERLAPPEDWINDOW, 0, 0, 200, 50, 0, 0, 0, None)
    win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, 0, TEXT)
    yield hwnd
    win32gui.DestroyWindow(hwnd)


def request(text=TEXT, offset=5, error="are"):
    return ReplaceRequest((1,), "w", text, offset, len(error), error, "is")


def test_selects_flagged_text(edit_hwnd):
    text_replace._select_with_win32(edit_hwnd, request())
    assert win32_edit.get_selection(edit_hwnd) == (5, 8)


def test_refuses_when_text_changed(edit_hwnd):
    win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, "Totally different")
    with pytest.raises(ReplaceError, match="changed"):
        text_replace._select_with_win32(edit_hwnd, request())


def test_refuses_non_edit_window():
    hwnd = win32gui.CreateWindowEx(0, "STATIC", "", 0, 0, 0, 10, 10, 0, 0, 0, None)
    try:
        with pytest.raises(ReplaceError, match="select text"):
            text_replace._select_with_win32(hwnd, request())
    finally:
        win32gui.DestroyWindow(hwnd)
