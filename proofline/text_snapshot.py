"""Plain data types describing the focused text field, plus the typing-pause detector.

Nothing here touches Windows APIs, so it can be unit tested anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from proofline.logging_setup import text_logging_enabled

PREVIEW_CHARS = 40
MAX_CLASS_CHARS = 40
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


@dataclass(frozen=True)
class ScreenRect:
    """Rectangle in physical screen pixels."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def is_empty(self) -> bool:
        # A caret is legitimately ~0-1 px wide, so only height decides emptiness.
        return self.height <= 0


@dataclass(frozen=True)
class FieldSnapshot:
    """The state of an editable text field at one moment."""

    field_id: tuple[int, ...]
    hwnd: int
    process_id: int
    process_name: str
    window_title: str
    control_type: str
    class_name: str
    text: str
    field_rect: ScreenRect
    caret_rect: ScreenRect | None
    caret_source: str

    def describe(self) -> str:
        return (
            f"{self.process_name} {self.control_type} "
            f"class={self.class_name[:MAX_CLASS_CHARS]!r} "
            f"window={self.window_title!r} hwnd={self.hwnd:#x}"
        )


@dataclass(frozen=True)
class FocusResult:
    """What the reader found: a snapshot when the focus is a usable text field."""

    focus_key: tuple[int, ...]
    description: str
    reason: str
    snapshot: FieldSnapshot | None = None
    hint: object | None = None  # setup_hints.SetupHint when the app needs a setting turned on
    # Diagnostics for the field picker (filled whenever an element has focus).
    process_name: str = ""
    window_title: str = ""
    signature: str = ""  # config.field_signature() of the resolved element
    patterns: str = ""  # "Text+Value", "Value", "Win32 edit", "none"; only when diagnosing


def loggable(text: str) -> str:
    """Length only by default; a short preview in debug mode."""
    return preview(text) if text_logging_enabled() else f"{len(text)} chars"


def word_count(text: str) -> int:
    """Words in text; zero-width characters (some empty editors hold one) don't count."""
    return len(text.translate(ZERO_WIDTH).split())


def preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    """Short, single-line summary for logs; never logs more than `limit` characters."""
    sample = text[:limit].replace("\r", " ").replace("\n", " ")
    suffix = "…" if len(text) > limit else ""
    return f"{len(text)} chars {sample!r}{suffix}"


class TypingDebouncer:
    """Report a field's text once it has stayed unchanged for `delay_s` seconds.

    A text is reported once while it stays in the field, so an idle field is not
    re-checked on every poll. After an edit, even back to a text already reported, it is
    reported again: the overlay drops its results on every change and waits for a new check.
    """

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s
        self._field_id: tuple[int, ...] | None = None
        self._text: str | None = None
        self._changed_at = 0.0
        self._reported_text: str | None = None

    def update(self, snapshot: FieldSnapshot | None, now: float) -> FieldSnapshot | None:
        if snapshot is None:
            self._field_id = None
            self._text = None
            self._reported_text = None
            return None
        if snapshot.field_id != self._field_id:
            self._field_id = snapshot.field_id
            self._reported_text = None
            self._text = None
        if snapshot.text != self._text:
            self._text = snapshot.text
            self._changed_at = now
            self._reported_text = None
            return None
        if snapshot.text == self._reported_text or now - self._changed_at < self._delay_s:
            return None
        self._reported_text = snapshot.text
        return snapshot
