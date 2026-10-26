"""Plain data for the underlines drawn under flagged words, plus the rectangle clean-up.

The monitor thread measures where each flagged span sits on screen (underline_rects.py);
the overlay controller turns the result into logical coordinates for the overlay window.
Nothing here touches Windows APIs.

Measured 2026-10-25 in Edge 156 (textarea, contenteditable) and Windows 11 Notepad: text
ranges map onto the right words, including wrapped lines and text after an emoji. Edge also
returns 1 px slivers for text scrolled out of view (pinned to the field's bottom edge) and for
the position just before a line start, so rectangles under MIN_RECT_PX are dropped.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from proofline.lt_client import Match
from proofline.text_snapshot import FieldSnapshot, ScreenRect

MIN_RECT_PX = 3
MAX_UNDERLINES = 50  # each span costs 1-6 ms of UI Automation calls per poll


@dataclass(frozen=True)
class Span:
    """A flagged stretch of the checked text; text is what it must read to be underlined."""

    offset: int
    length: int
    text: str


@dataclass(frozen=True)
class UnderlineTarget:
    """What to measure: these spans, while the field still holds exactly this text."""

    field_id: tuple[int, ...]
    text: str
    spans: tuple[Span, ...]

    def applies_to(self, snapshot: FieldSnapshot | None) -> bool:
        return snapshot is not None and (snapshot.field_id, snapshot.text) == (self.field_id, self.text)


@dataclass(frozen=True)
class Underlines:
    """Measured rectangles, in physical pixels, one tuple per span of the target."""

    field_id: tuple[int, ...]
    text: str
    field_rect: ScreenRect
    rects: tuple[tuple[ScreenRect, ...], ...]
    spans: tuple[Span, ...]  # what was measured; a target with other spans (AI findings arrived) does not match

    def matches(self, target: UnderlineTarget | None) -> bool:
        return target is not None and (self.field_id, self.text, self.spans) == (
            target.field_id, target.text, target.spans)


def underlined_matches(matches: Sequence[Match]) -> tuple[Match, ...]:
    """The matches that get a line, in text order: span i of target_for() is match i here."""
    ordered = sorted((m for m in matches if m.length > 0), key=lambda m: (m.offset, m.length))
    return tuple(ordered[:MAX_UNDERLINES])


def target_for(snapshot: FieldSnapshot | None, matches: Sequence[Match]) -> UnderlineTarget | None:
    """The spans to underline for these matches, in text order; None when there is nothing."""
    if snapshot is None:
        return None
    spans = tuple(Span(m.offset, m.length, m.error_text) for m in underlined_matches(matches))
    return UnderlineTarget(snapshot.field_id, snapshot.text, spans) if spans else None


def span_at(underlines: Underlines, caret: ScreenRect) -> tuple[int, ScreenRect] | None:
    """(span index, word rectangle) when the caret is inside a measured word.

    The caret just after a word's last letter does not count, so finishing a flagged word
    and pausing does not open the card; at its first letter or inside it does.
    """
    middle = (caret.top + caret.bottom) // 2
    for index, rects in enumerate(underlines.rects):
        for rect in rects:
            if rect.left <= caret.left < rect.right - 1 and rect.top <= middle <= rect.bottom:
                return index, rect
    return None


def clean_rects(rects: Iterable[ScreenRect], field: ScreenRect) -> tuple[ScreenRect, ...]:
    """Clip to the field and drop slivers (scrolled-out text, line-start positions)."""
    kept = []
    for rect in rects:
        clipped = ScreenRect(
            max(rect.left, field.left), max(rect.top, field.top),
            min(rect.right, field.right), min(rect.bottom, field.bottom),
        )
        if clipped.width >= MIN_RECT_PX and clipped.height >= MIN_RECT_PX:
            kept.append(clipped)
    return tuple(kept)
