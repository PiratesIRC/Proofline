"""Select a flagged word in the focused field via UI Automation and paste the correction.

Runs on the monitor thread (UIA objects cannot cross threads). Every step is verified
and the operation aborts rather than paste into the wrong place.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import comtypes
import uiautomation as auto

from proofline import win32_edit
from proofline.clipboard import ClipboardError, paste_text
from proofline.replace_request import ReplaceError, ReplaceRequest
from proofline.uia_reader import (
    MAX_TEXT_CHARS,
    foreground_window_title,
    resolve_editable,
)
from proofline.win32_edit import Win32EditError

log = logging.getLogger(__name__)

START = auto.TextPatternRangeEndpoint.Start
END = auto.TextPatternRangeEndpoint.End
CHARACTER = auto.TextUnit.Character
# Chromium (Edge, Chrome, WebView2) applies Select() asynchronously in the renderer;
# the new selection typically becomes visible to UIA after ~30 ms.
SELECTION_TIMEOUT_S = 0.5
SELECTION_POLL_S = 0.02
MS_PER_S = 1000


def replace_in_focused_field(request: ReplaceRequest) -> None:
    """Apply the correction or raise ReplaceError explaining why it was not applied."""
    try:
        control = _verified_control(request)
        text_pattern = control.GetPattern(auto.PatternId.TextPattern)
        if text_pattern is None:
            _select_with_win32(control.NativeWindowHandle, request)
        else:
            _select_with_uia(text_pattern, request)
        paste_text(request.replacement)
    except comtypes.COMError as exc:
        log.warning("UIA error while replacing: %s", exc)
        raise ReplaceError("The text field stopped responding; try again.") from exc
    except (ClipboardError, Win32EditError) as exc:
        raise ReplaceError(str(exc)) from exc
    log.info("Replaced %d chars at offset %d", request.length, request.offset)


def _verified_control(request: ReplaceRequest) -> auto.Control:
    focused = auto.GetFocusedControl()
    control = None
    if focused is not None:
        # A custom field is the focused element itself; otherwise resolve like the reader.
        is_target = tuple(focused.GetRuntimeId() or ()) == request.field_id
        control = focused if is_target else resolve_editable(focused)
    if control is None or tuple(control.GetRuntimeId() or ()) != request.field_id:
        raise ReplaceError("The text field no longer has focus.")
    if foreground_window_title() != request.window_title:
        raise ReplaceError("A different window is now active.")
    return control


def _check_unchanged(current: str, request: ReplaceRequest) -> None:
    if current[request.offset : request.offset + request.length] != request.error_text:
        raise ReplaceError("The text has changed since it was checked.")


def _select_with_uia(text_pattern: object, request: ReplaceRequest) -> None:
    _check_unchanged(text_pattern.DocumentRange.GetText(MAX_TEXT_CHARS), request)
    _locate(text_pattern, request).Select()
    _verify_selection(text_pattern, request)


def _select_with_win32(hwnd: int, request: ReplaceRequest) -> None:
    """Classic Edit/RichEdit without TextPattern: select with EM_SETSEL."""
    if not win32_edit.is_classic_edit(hwnd):
        raise ReplaceError("This app does not let other programs select text, so the fix can't be applied.")
    _check_unchanged(win32_edit.read_text(hwnd, MAX_TEXT_CHARS), request)
    start, end = request.offset, request.offset + request.length
    win32_edit.set_selection(hwnd, start, end)
    if win32_edit.get_selection(hwnd) != (start, end):
        raise ReplaceError("Could not select the flagged text, so nothing was changed.")


def _locate(text_pattern: object, request: ReplaceRequest) -> object:
    """Find the raw UIA range covering the error: by character offset, else by search."""
    document = text_pattern.DocumentRange.textRange
    by_offset = _range_by_offset(document, request.offset, request.length)
    if _range_text(by_offset) == request.error_text:
        return by_offset
    log.debug("Offset-based range did not match; falling back to text search")
    by_search = _range_by_search(document, request)
    if by_search is None or _range_text(by_search) != request.error_text:
        raise ReplaceError("Could not find the flagged text in the field.")
    return by_search


def _range_by_offset(document: object, offset: int, length: int) -> object:
    rng = document.Clone()
    rng.MoveEndpointByRange(END, rng, START)  # collapse to the start of the document
    rng.Move(CHARACTER, offset)
    rng.MoveEndpointByUnit(END, CHARACTER, length)
    return rng


def _range_by_search(document: object, request: ReplaceRequest) -> object | None:
    """The n-th occurrence of the error text, where n is how often it appears before offset."""
    occurrence = request.text[: request.offset].count(request.error_text)
    search = document.Clone()
    found = None
    for _ in range(occurrence + 1):
        found = search.FindText(request.error_text, False, False)
        if not found:
            return None
        search.MoveEndpointByRange(START, found, END)
    return found


def _range_text(raw_range: object) -> str:
    return raw_range.GetText(-1) if raw_range else ""


def _verify_selection(
    text_pattern: object,
    request: ReplaceRequest,
    timeout_s: float = SELECTION_TIMEOUT_S,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait until the app reports exactly the flagged text as selected."""
    started = clock()
    while True:
        selections = text_pattern.GetSelection()
        selected = selections[0].GetText(-1) if selections else ""
        elapsed_ms = (clock() - started) * MS_PER_S
        if selected == request.error_text:
            log.debug("Selection confirmed after %.0f ms", elapsed_ms)
            return
        if elapsed_ms >= timeout_s * MS_PER_S:
            log.warning(
                "Selection mismatch after %.0f ms: expected %d chars, got %d",
                elapsed_ms,
                request.length,
                len(selected),
            )
            raise ReplaceError("Could not select the flagged text, so nothing was changed.")
        sleep(SELECTION_POLL_S)
