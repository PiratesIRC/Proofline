"""Measure where flagged spans of the focused field sit on screen (UI Automation).

Monitor thread only: import inside TextMonitor.run(), like uia_reader and text_replace.
"""

from __future__ import annotations

import uiautomation as auto

from proofline import uia_reader
from proofline.text_snapshot import ScreenRect
from proofline.underlines import Underlines, UnderlineTarget, clean_rects

START = auto.TextPatternRangeEndpoint.Start
END = auto.TextPatternRangeEndpoint.End
CHARACTER = auto.TextUnit.Character


def anchor(target: UnderlineTarget) -> tuple[object, ...] | None:
    """Where the field, and its first flagged span if any, sit now: a cheap check for scrolling.

    Asks for the focused element again on every call. An element fetched earlier can keep
    reporting where the text was when it was fetched (Edge, measured 2026-11-26), while a fresh
    one followed a mouse-wheel scroll, moving every 220-300 ms; one read costs about 4-6 ms.
    None when the field lost focus.
    """
    focused = auto.GetFocusedControl()
    if focused is None:
        return None
    control = uia_reader.resolve_editable(focused)
    if tuple(control.GetRuntimeId() or ()) != target.field_id:
        return None
    box = control.BoundingRectangle
    field = (box.left, box.top, box.right, box.bottom)
    return (field, _first_span_corner(control, target))


def _first_span_corner(control: auto.Control, target: UnderlineTarget) -> tuple[int, int] | None:
    """Top-left corner of the first span's first rectangle; None without spans or rectangles."""
    if not target.spans:
        return None
    pattern = control.GetPattern(auto.PatternId.TextPattern)
    if pattern is None:
        return None
    span = target.spans[0]
    rng = pattern.DocumentRange.textRange.Clone()
    rng.MoveEndpointByRange(END, rng, START)  # collapse to the start of the text
    if rng.Move(CHARACTER, span.offset) != span.offset:
        return None
    rng.MoveEndpointByUnit(END, CHARACTER, span.length)
    rects = auto.TextRange(textRange=rng).GetBoundingRectangles()
    return (rects[0].left, rects[0].top) if rects else None


def measure(target: UnderlineTarget) -> Underlines | None:
    """Rectangles for each span of target in the field the reader last resolved.

    None when that field is gone or has no TextPattern (classic Win32 edits keep only the
    badge). A span whose range no longer reads as its text gets no rectangles.
    """
    control = uia_reader.last_control()
    if control is None or tuple(control.GetRuntimeId() or ()) != target.field_id:
        return None
    pattern = control.GetPattern(auto.PatternId.TextPattern)
    if pattern is None:
        return None
    bounds = control.BoundingRectangle
    field = ScreenRect(bounds.left, bounds.top, bounds.right, bounds.bottom)
    cursor = pattern.DocumentRange.textRange.Clone()
    cursor.MoveEndpointByRange(END, cursor, START)  # collapse to the start of the text
    position = 0
    measured = []
    for span in target.spans:  # in text order, so the cursor only moves forward
        position += cursor.Move(CHARACTER, span.offset - position)
        rng = cursor.Clone()
        rng.MoveEndpointByUnit(END, CHARACTER, span.length)
        if position != span.offset or rng.GetText(-1) != span.text:
            measured.append(())
            continue
        rects = auto.TextRange(textRange=rng).GetBoundingRectangles()
        measured.append(clean_rects((ScreenRect(r.left, r.top, r.right, r.bottom) for r in rects), field))
    return Underlines(target.field_id, target.text, field, tuple(measured), target.spans)
