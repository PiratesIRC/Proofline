"""A focused window whose program stopped responding is skipped before any UIA call can block."""

from __future__ import annotations

import pytest

from proofline import text_replace, uia_reader
from proofline.replace_request import ReplaceError, ReplaceRequest

HUNG_HWND = 4242


@pytest.fixture
def hung(monkeypatch):
    monkeypatch.setattr(uia_reader.window_response, "focused_window", lambda: HUNG_HWND)
    monkeypatch.setattr(uia_reader.window_response, "not_responding", lambda hwnd: hwnd == HUNG_HWND)

    def no_uia():
        raise AssertionError("UIA was called for a window that does not respond")

    monkeypatch.setattr(uia_reader.auto, "GetFocusedControl", no_uia)


def test_the_reader_skips_a_window_that_does_not_respond(hung):
    result = uia_reader.read_focused_field()
    assert result.reason == uia_reader.NOT_RESPONDING_REASON
    assert result.snapshot is None
    assert uia_reader.last_control() is None


def test_a_correction_is_refused_for_a_window_that_does_not_respond(hung):
    request = ReplaceRequest(field_id=(1, 2), window_title="t", text="a b", offset=0, length=1,
                             error_text="a", replacement="c")
    with pytest.raises(ReplaceError, match="not responding"):
        text_replace.replace_in_focused_field(request)
