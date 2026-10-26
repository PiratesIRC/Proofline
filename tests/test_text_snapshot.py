import pytest
from factories import snapshot

from proofline.text_snapshot import (
    ScreenRect,
    TypingDebouncer,
    loggable,
    preview,
    word_count,
)

DELAY = 1.0


def test_screen_rect_dimensions_and_caret_width_zero_is_not_empty():
    rect = ScreenRect(10, 20, 10, 40)
    assert (rect.width, rect.height) == (0, 20)
    assert not rect.is_empty
    assert ScreenRect(0, 5, 10, 5).is_empty


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("short", "5 chars 'short'"),
        ("line1\r\nline2", "12 chars 'line1  line2'"),
        ("x" * 50, f"50 chars '{'x' * 40}'…"),
    ],
)
def test_preview_is_single_line_and_truncated(text, expected):
    assert preview(text) == expected


def test_describe_includes_app_and_window():
    text = snapshot().describe()
    assert "notepad.exe" in text
    assert "notes.txt - Notepad" in text


def test_debouncer_reports_after_pause_once():
    debouncer = TypingDebouncer(DELAY)
    snap = snapshot()
    assert debouncer.update(snap, 0.0) is None  # first sight starts the timer
    assert debouncer.update(snap, 0.5) is None  # not paused long enough
    assert debouncer.update(snap, 1.0) == snap
    assert debouncer.update(snap, 5.0) is None  # same text is not re-reported


def test_debouncer_restarts_timer_while_typing():
    debouncer = TypingDebouncer(DELAY)
    debouncer.update(snapshot(text="Th"), 0.0)
    debouncer.update(snapshot(text="This"), 0.8)
    assert debouncer.update(snapshot(text="This"), 1.5) is None
    assert debouncer.update(snapshot(text="This"), 1.8).text == "This"


def test_debouncer_reports_again_after_edit():
    debouncer = TypingDebouncer(DELAY)
    debouncer.update(snapshot(text="a"), 0.0)
    debouncer.update(snapshot(text="a"), 1.0)
    debouncer.update(snapshot(text="ab"), 2.0)
    assert debouncer.update(snapshot(text="ab"), 3.0).text == "ab"


def test_debouncer_rechecks_when_returning_to_a_field():
    debouncer = TypingDebouncer(DELAY)
    first, other = snapshot(), snapshot(field_id=(9,))
    debouncer.update(first, 0.0)
    debouncer.update(first, 1.0)
    debouncer.update(other, 2.0)
    debouncer.update(first, 3.0)
    assert debouncer.update(first, 4.0) == first


def test_debouncer_resets_when_focus_leaves_text():
    debouncer = TypingDebouncer(DELAY)
    snap = snapshot()
    debouncer.update(snap, 0.0)
    assert debouncer.update(None, 0.5) is None
    assert debouncer.update(snap, 1.2) is None  # timer restarted
    assert debouncer.update(snap, 2.2) == snap


def test_loggable_hides_text_by_default(monkeypatch):
    monkeypatch.delenv("PROOFLINE_LOG_TEXT", raising=False)
    assert loggable("secret case notes") == "17 chars"


def test_loggable_shows_preview_when_opted_in(monkeypatch):
    monkeypatch.setenv("PROOFLINE_LOG_TEXT", "1")
    assert loggable("hello") == "5 chars 'hello'"


@pytest.mark.parametrize(("text", "count"), [("", 0), ("  \n", 0), ("\ufeff", 0), ("one\u200b two", 2)])
def test_word_count_ignores_zero_width_characters(text, count):
    assert word_count(text) == count
