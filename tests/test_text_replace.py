import pytest

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
