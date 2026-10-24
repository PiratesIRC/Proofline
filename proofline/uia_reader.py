"""Read the focused text field through Windows UI Automation.

Import this module only on the thread that will use it: uiautomation sets the
process DPI awareness on import, and UIA objects cannot cross threads.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from dataclasses import replace
from functools import lru_cache

import comtypes
import uiautomation as auto

from proofline import win32_edit
from proofline.app_names import process_path
from proofline.config import custom_field_matches, field_signature
from proofline.field_filters import FieldTraits
from proofline.field_filters import skip_reason as field_skip_reason
from proofline.setup_hints import hint_for
from proofline.text_snapshot import FieldSnapshot, FocusResult, ScreenRect

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 20_000
MAX_NAME_CHARS = 40
# Search boxes with suggestion lists are ComboBoxes; they count only when they expose
# editable text (TextPattern), which plain dropdowns such as <select> do not.
EDITABLE_TYPES = frozenset(
    {auto.ControlType.EditControl, auto.ControlType.DocumentControl, auto.ControlType.ComboBoxControl}
)
# Rich web editors sometimes put focus on an inner element; walk up this far to find
# the editable Edit/Document that owns it.
INNER_TYPES = frozenset(
    {
        auto.ControlType.TextControl,
        auto.ControlType.GroupControl,
        auto.ControlType.CustomControl,
        auto.ControlType.PaneControl,
    }
)
MAX_ANCESTOR_STEPS = 4
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20
ERROR_ACCESS_DENIED = 5
ELEVATED_REASON = "app runs as administrator; Windows blocks reading it from a normal app"
GA_ROOT = 2
MAX_TITLE_CHARS = 512

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_advapi32 = ctypes.windll.advapi32


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def read_focused_field(custom_fields: tuple[str, ...] = (), diagnose: bool = False) -> FocusResult:
    """Describe the focused element and, if it is an editable text field, snapshot it.

    custom_fields are field signatures the user asked to check even when they don't
    look like text boxes; diagnose adds the supported patterns for the field picker.
    """
    try:
        focused = auto.GetFocusedControl()
        if focused is None:
            return FocusResult((), "nothing", "no focused element")
        if custom_field_matches(_signature(focused), custom_fields):
            control = focused
        else:
            control = resolve_editable(focused)
        is_custom = custom_field_matches(_signature(control), custom_fields)
        result = _read(control, is_custom)
        return replace(
            result,
            process_name=process_name(control.ProcessId),
            window_title=foreground_window_title(),
            signature=_signature(control),
            patterns=_pattern_summary(control) if diagnose else "",
        )
    except comtypes.COMError as exc:
        # Elements vanish constantly (windows closing, pages navigating).
        return FocusResult((), "unknown", f"UIA error: {exc}")


def _read(control: auto.Control, is_custom: bool) -> FocusResult:
    focus_key = tuple(control.GetRuntimeId() or ())
    description = describe_control(control)
    reason = _skip_reason(control, is_custom)
    if reason:
        return FocusResult(focus_key, description, reason, hint=_hint(control, is_text_field=False))
    return _snapshot(control, focus_key, description, is_custom)


def _signature(control: auto.Control) -> str:
    return field_signature(process_name(control.ProcessId), control.ControlTypeName, control.ClassName or "")


def _pattern_summary(control: auto.Control) -> str:
    names = [
        name
        for name, pattern_id in (("Text", auto.PatternId.TextPattern), ("Value", auto.PatternId.ValuePattern))
        if control.GetPattern(pattern_id) is not None
    ]
    if names:
        return "+".join(names)
    return "Win32 edit" if win32_edit.is_classic_edit(control.NativeWindowHandle) else "none"


def resolve_editable(focused: auto.Control) -> auto.Control:
    """The focused element, or the editable Edit/Document ancestor of an inner element."""
    if focused.ControlType not in INNER_TYPES:
        return focused
    current = focused
    for _ in range(MAX_ANCESTOR_STEPS):
        current = current.GetParentControl()
        if current is None:
            break
        if current.ControlType in EDITABLE_TYPES:
            log.debug("Focus is inside %s; using that ancestor", current.ControlTypeName)
            return current
    return focused


def describe_control(control: auto.Control) -> str:
    name = (control.Name or "")[:MAX_NAME_CHARS]
    return (
        f"{process_name(control.ProcessId)} {control.ControlTypeName} "
        f"class={control.ClassName[:MAX_NAME_CHARS]!r} framework={control.FrameworkId!r} "
        f"name={name!r} hwnd={control.NativeWindowHandle:#x}"
    )


def _skip_reason(control: auto.Control, is_custom: bool = False) -> str:
    if control.ProcessId == os.getpid():
        return "focus is in this app"
    if is_elevated(control.ProcessId):
        return ELEVATED_REASON
    if control.ControlType not in EDITABLE_TYPES and not is_custom:
        return f"not a text control ({control.ControlTypeName})"
    if control.IsPassword:
        return "password field"
    return ""


def _snapshot(
    control: auto.Control, focus_key: tuple[int, ...], description: str, is_custom: bool = False
) -> FocusResult:
    text_pattern = control.GetPattern(auto.PatternId.TextPattern)
    value_pattern = control.GetPattern(auto.PatternId.ValuePattern)
    if control.ControlType == auto.ControlType.ComboBoxControl and text_pattern is None and not is_custom:
        return FocusResult(focus_key, description, "dropdown without editable text")
    if text_pattern is None and value_pattern is None:
        if not win32_edit.is_classic_edit(control.NativeWindowHandle):
            hint = _hint(control, is_text_field=False)
            return FocusResult(focus_key, description, "no Text or Value pattern", hint=hint)
    elif _is_read_only(text_pattern, value_pattern):
        return FocusResult(focus_key, description, "read-only", hint=_hint(control, is_text_field=False))
    reason = "" if is_custom else field_skip_reason(_traits(control))
    if reason:
        return FocusResult(focus_key, description, reason)

    text = _read_text(text_pattern, value_pattern, control.NativeWindowHandle)
    caret_rect, caret_source = find_caret(control, text_pattern)
    bounds = control.BoundingRectangle
    snapshot = FieldSnapshot(
        field_id=focus_key,
        hwnd=control.NativeWindowHandle,
        process_id=control.ProcessId,
        process_name=process_name(control.ProcessId),
        window_title=foreground_window_title(),
        control_type=control.ControlTypeName,
        class_name=control.ClassName,
        text=text,
        field_rect=ScreenRect(bounds.left, bounds.top, bounds.right, bounds.bottom),
        caret_rect=caret_rect,
        caret_source=caret_source,
    )
    pattern_names = "+".join(
        name for name, p in (("Text", text_pattern), ("Value", value_pattern)) if p is not None
    ) or "Win32 messages"
    return FocusResult(focus_key, description, f"ok via {pattern_names}", snapshot)


def _is_read_only(text_pattern: object, value_pattern: object) -> bool:
    if value_pattern is not None:
        return bool(value_pattern.IsReadOnly)
    value = text_pattern.DocumentRange.GetAttributeValue(auto.TextAttributeId.IsReadOnlyAttribute)
    # Anything other than a definite False (mixed, not supported) is treated as editable.
    return value is True


def _read_text(text_pattern: object, value_pattern: object, hwnd: int) -> str:
    if text_pattern is not None:
        return text_pattern.DocumentRange.GetText(MAX_TEXT_CHARS)
    if value_pattern is not None:
        return (value_pattern.Value or "")[:MAX_TEXT_CHARS]
    return win32_edit.read_text(hwnd, MAX_TEXT_CHARS)


def _traits(control: auto.Control) -> FieldTraits:
    return FieldTraits(
        control_type=control.ControlTypeName,
        class_name=control.ClassName or "",
        name=control.Name or "",
        help_text=control.HelpText or "",
        automation_id=control.AutomationId or "",
        has_range_value=control.GetPattern(auto.PatternId.RangeValuePattern) is not None,
    )


def _hint(control: auto.Control, is_text_field: bool) -> object | None:
    try:
        return hint_for(
            process_name(control.ProcessId),
            foreground_window_title(),
            control.FrameworkId or "",
            control.ClassName or "",
            is_text_field,
            process_path(control.ProcessId),
        )
    except comtypes.COMError:
        return None


def find_caret(control: auto.Control, text_pattern: object) -> tuple[ScreenRect | None, str]:
    """Try each caret strategy in order of accuracy; return the rect and the strategy name."""
    strategies = (
        ("uia-caret", lambda: _caret_from_text_pattern2(control)),
        ("uia-selection", lambda: _caret_from_selection(text_pattern)),
        ("win32-caret", _caret_from_win32),
    )
    for source, strategy in strategies:
        try:
            rect = strategy()
        except (comtypes.COMError, OSError, ValueError) as exc:
            log.debug("Caret strategy %s failed: %s", source, exc)
            continue
        if rect is not None and not rect.is_empty:
            return rect, source
    return None, "none"


def _caret_from_text_pattern2(control: auto.Control) -> ScreenRect | None:
    pattern2 = control.GetPattern(auto.PatternId.TextPattern2)
    if pattern2 is None:
        return None
    result = pattern2.pattern.GetCaretRange()
    raw_range = result[-1] if isinstance(result, tuple) else result
    return _caret_rect_from_range(raw_range) if raw_range else None


def _caret_from_selection(text_pattern: object) -> ScreenRect | None:
    if text_pattern is None:
        return None
    selections = text_pattern.GetSelection()
    return _caret_rect_from_range(selections[0].textRange) if selections else None


def _caret_rect_from_range(raw_range: object) -> ScreenRect | None:
    """Caret rect at the end of a range. Degenerate ranges often report no rectangles,
    so measure the neighbouring character instead."""
    caret = raw_range.Clone()
    caret.MoveEndpointByRange(
        auto.TextPatternRangeEndpoint.Start, caret, auto.TextPatternRangeEndpoint.End
    )
    rect = _first_rect(caret)
    if rect:
        return ScreenRect(rect.left, rect.top, rect.left + 1, rect.bottom)

    next_char = caret.Clone()
    if next_char.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.End, auto.TextUnit.Character, 1):
        rect = _first_rect(next_char)
        if rect:
            return ScreenRect(rect.left, rect.top, rect.left + 1, rect.bottom)

    prev_char = caret.Clone()
    if prev_char.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.Start, auto.TextUnit.Character, -1):
        rect = _first_rect(prev_char)
        if rect:
            return ScreenRect(rect.right, rect.top, rect.right + 1, rect.bottom)
    return None


def _first_rect(raw_range: object) -> auto.Rect | None:
    rects = auto.TextRange(textRange=raw_range).GetBoundingRectangles()
    return rects[0] if rects and rects[0].height() > 0 else None


def _caret_from_win32() -> ScreenRect | None:
    """System caret of the foreground thread (classic Win32 and many legacy apps)."""
    info = _GuiThreadInfo(cbSize=ctypes.sizeof(_GuiThreadInfo))
    if not _user32.GetGUIThreadInfo(0, ctypes.byref(info)) or not info.hwndCaret:
        return None
    corners = (wintypes.POINT * 2)(
        wintypes.POINT(info.rcCaret.left, info.rcCaret.top),
        wintypes.POINT(info.rcCaret.right, info.rcCaret.bottom),
    )
    _user32.MapWindowPoints(info.hwndCaret, None, corners, 2)
    return ScreenRect(corners[0].x, corners[0].y, corners[1].x, corners[1].y)


def foreground_window_title() -> str:
    """Title of the top-level window that owns the keyboard focus."""
    hwnd = _user32.GetAncestor(_user32.GetForegroundWindow(), GA_ROOT)
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(MAX_TITLE_CHARS)
    _user32.GetWindowTextW(hwnd, buffer, MAX_TITLE_CHARS)
    return buffer.value


def process_name(pid: int) -> str:
    return os.path.basename(process_path(pid)) or f"pid{pid}"


@lru_cache(maxsize=256)
def is_elevated(pid: int) -> bool:
    """True if the process runs at a higher privilege level than this app (UIPI blocks it)."""
    if _token_is_elevated(os.getpid()):
        return False  # an elevated client can read everything
    return _token_is_elevated(pid)


def _token_is_elevated(pid: int) -> bool:
    process = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return False
    token = wintypes.HANDLE()
    try:
        if not _advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            # A normal process may not open an elevated process's token.
            return ctypes.GetLastError() == ERROR_ACCESS_DENIED
        elevated = wintypes.DWORD()
        size = wintypes.DWORD()
        ok = _advapi32.GetTokenInformation(
            token, TOKEN_ELEVATION_CLASS, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)
        )
        return bool(ok and elevated.value)
    finally:
        if token:
            _kernel32.CloseHandle(token)
        _kernel32.CloseHandle(process)
