"""text_replace waits for the field to change after Ctrl+V before the clipboard goes back."""

from __future__ import annotations

import logging

from proofline import text_replace


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_waiter(monkeypatch, texts, responding):
    """texts: what each read of the field returns; responding: answers of the not-responding check."""
    reads, checks = iter(texts), iter(responding)
    monkeypatch.setattr(text_replace.window_response, "focused_window", lambda: 7)
    monkeypatch.setattr(text_replace.window_response, "not_responding", lambda hwnd: not next(checks, True))
    clock = FakeClock()
    read_count = []

    def read() -> str:
        read_count.append(1)
        return next(reads)

    waiter = text_replace.paste_waiter(read, "This are fine.", clock=clock, sleep=clock.sleep)
    return waiter, clock, read_count


def test_returns_as_soon_as_the_field_shows_a_change(monkeypatch):
    waiter, clock, reads = make_waiter(monkeypatch, ["This are fine.", "This is fine."], [True, True])
    waiter()
    assert len(reads) == 2
    assert clock.now < 0.1


def test_does_not_read_while_the_program_does_not_respond(monkeypatch):
    """A UIA read of a program that does not respond would block (see window_response)."""
    waiter, _clock, reads = make_waiter(monkeypatch, ["This is fine."], [False, False, False, True])
    waiter()
    assert len(reads) == 1  # read only once it answered


def test_gives_up_after_the_limit_and_says_so(monkeypatch, caplog):
    waiter, clock, _reads = make_waiter(monkeypatch, ["This are fine."] * 1000, [True] * 1000)
    with caplog.at_level(logging.WARNING):
        waiter()
    assert text_replace.PASTE_CONFIRM_S <= clock.now < text_replace.PASTE_CONFIRM_S + 0.2
    assert "did not change" in caplog.text


def test_a_read_error_counts_as_not_changed_yet(monkeypatch):
    texts = iter([OSError("element gone"), "This is fine."])

    def flaky() -> str:
        item = next(texts)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(text_replace.window_response, "focused_window", lambda: 7)
    monkeypatch.setattr(text_replace.window_response, "not_responding", lambda hwnd: False)
    clock = FakeClock()
    text_replace.paste_waiter(flaky, "This are fine.", clock=clock, sleep=clock.sleep)()
    assert clock.now < text_replace.PASTE_CONFIRM_S
