from types import SimpleNamespace

import pytest

from proofline import text_replace
from proofline.replace_request import ReplaceError, ReplaceRequest
from proofline.text_replace import _verify_selection

REQUEST = ReplaceRequest((1,), "w", "a speling b", 2, 7, "speling", "spelling")


class FakeRange:
    def __init__(self, text):
        self.text = text

    def GetText(self, _max):
        return self.text


class FakeTextPattern:
    """Reports an empty selection for the first `delay_polls` reads (like Chromium)."""

    def __init__(self, final, delay_polls):
        self.final = final
        self.delay_polls = delay_polls
        self.polls = 0

    def GetSelection(self):
        self.polls += 1
        text = self.final if self.polls > self.delay_polls else ""
        return [FakeRange(text)]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_waits_for_asynchronous_selection():
    pattern = FakeTextPattern("speling", delay_polls=2)
    clock = FakeClock()
    _verify_selection(pattern, REQUEST, clock=clock, sleep=clock.sleep)
    assert pattern.polls == 3


@pytest.mark.parametrize("final", ["", "spel", "other"])
def test_gives_up_after_timeout_when_selection_never_matches(final):
    pattern = FakeTextPattern(final, delay_polls=0)
    clock = FakeClock()
    with pytest.raises(ReplaceError, match="Could not select"):
        _verify_selection(pattern, REQUEST, timeout_s=0.5, clock=clock, sleep=clock.sleep)
    assert clock.now >= 0.5


class FakeControl:
    NativeWindowHandle = 0

    def GetRuntimeId(self):
        return [1]

    def GetPattern(self, _pattern_id):
        return SimpleNamespace(DocumentRange=SimpleNamespace(GetText=lambda _max: "field text"))


@pytest.fixture
def window_switch_during_selection(monkeypatch):
    """The field and window are right when the fix starts; another window is in front once the
    selection is confirmed. Records the keystrokes that reach the 'keyboard'."""
    titles = iter(["w", "other window"])
    sent = []
    # The real check would message whatever window is in front on the test machine's desktop.
    monkeypatch.setattr(text_replace.window_response, "not_responding", lambda hwnd: False)
    monkeypatch.setattr(text_replace.auto, "GetFocusedControl", FakeControl)
    monkeypatch.setattr(text_replace, "foreground_window_title", lambda: next(titles, "other window"))
    monkeypatch.setattr(text_replace, "_select_with_uia", lambda pattern, request: None)
    monkeypatch.setattr(text_replace, "send_delete", lambda: sent.append("delete"))
    monkeypatch.setattr(text_replace, "paste_text", lambda text, send_keys=None, wait_until_pasted=None: (
        send_keys() if send_keys else None, sent.append(f"paste {text}")))
    return sent


@pytest.mark.parametrize("replacement", ["is", ""])
def test_no_keys_are_sent_after_another_window_comes_to_the_front(window_switch_during_selection, replacement):
    request = ReplaceRequest((1,), "w", "This are a test.", 5, 3, "are", replacement)
    with pytest.raises(ReplaceError, match="different window"):
        text_replace.replace_in_focused_field(request)
    assert window_switch_during_selection == []
