import threading
from dataclasses import replace

import pytest
from factories import focus_result, snapshot

from proofline.config import Config
from proofline.lt_client import Match
from proofline.replace_request import ReplaceError, ReplaceRequest
from proofline.text_monitor import TextMonitor

FAST_POLL_S = 0.01
FAST_CONFIG = Config(debounce_ms=200)
MATCH = Match(5, 3, "msg", "", ("is",), "RULE", "Grammar", "are")


class ScriptedReader:
    """Returns the current FocusResult; tests swap it to simulate the user."""

    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.calls += 1
            if isinstance(self.result, Exception):
                raise self.result
            return self.result


class FakeReplacer:
    def __init__(self, error=None):
        self.requests = []
        self.error = error

    def __call__(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error


@pytest.fixture
def make_monitor(qtbot):
    monitors = []

    def make(reader, config=FAST_CONFIG):
        monitor = TextMonitor(
            config, reader=reader, replacer=FakeReplacer(), poll_interval_s=FAST_POLL_S
        )
        monitors.append(monitor)
        return monitor

    yield make
    for monitor in monitors:
        monitor.stop()


def test_emits_text_ready_after_typing_pause(qtbot, make_monitor):
    monitor = make_monitor(ScriptedReader(focus_result()))
    with qtbot.waitSignal(monitor.text_ready, timeout=2000) as blocker:
        monitor.start()
    assert blocker.args[0].text == "This are a test."


def test_field_changed_emitted_on_focus_and_text_change(qtbot, make_monitor):
    reader = ScriptedReader(focus_result())
    monitor = make_monitor(reader)
    seen = []
    monitor.field_changed.connect(seen.append)
    monitor.start()
    qtbot.waitUntil(lambda: len(seen) == 1)
    reader.result = focus_result(snapshot(text="This is a test."))
    qtbot.waitUntil(lambda: len(seen) == 2)
    reader.result = focus_result(None, reason="not a text control (ButtonControl)")
    qtbot.waitUntil(lambda: len(seen) == 3)
    assert seen[1].text == "This is a test."
    assert seen[2] is None


def test_disabled_app_produces_no_snapshot(qtbot, make_monitor):
    config = Config(debounce_ms=200, disabled_apps=("NOTEPAD.EXE",))
    reader = ScriptedReader(focus_result())
    monitor = make_monitor(reader, config)
    ready = []
    monitor.text_ready.connect(ready.append)
    monitor.start()
    qtbot.waitUntil(lambda: reader.calls > 30)
    assert ready == []


def test_paused_config_skips_reader_and_resumes(qtbot, make_monitor):
    reader = ScriptedReader(focus_result())
    monitor = make_monitor(reader, Config(debounce_ms=200, enabled=False))
    monitor.start()
    qtbot.wait(100)
    assert reader.calls == 0
    with qtbot.waitSignal(monitor.text_ready, timeout=2000):
        monitor.set_config(replace(monitor._config, enabled=True))


def test_reader_exceptions_are_logged_and_survived(qtbot, make_monitor, caplog):
    reader = ScriptedReader(RuntimeError("COM exploded"))
    monitor = make_monitor(reader)
    monitor.start()
    qtbot.waitUntil(lambda: reader.calls > 5)
    reader.result = focus_result()
    with qtbot.waitSignal(monitor.text_ready, timeout=2000):
        pass
    assert any("Reading the focused field failed" in r.getMessage() for r in caplog.records)


def test_stop_ends_thread(qtbot, make_monitor):
    monitor = make_monitor(ScriptedReader(focus_result()))
    monitor.start()
    monitor.stop()
    assert monitor.isFinished()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, [True, ""]),
        (ReplaceError("The text has changed since it was checked."), [False, "The text has changed since it was checked."]),
        (RuntimeError("boom"), [False, "Unexpected error; see the log for details."]),
    ],
)
def test_replace_requests_run_on_monitor_thread(qtbot, error, expected):
    replacer = FakeReplacer(error)
    monitor = TextMonitor(
        FAST_CONFIG, reader=ScriptedReader(focus_result()), replacer=replacer, poll_interval_s=FAST_POLL_S
    )
    request = ReplaceRequest.build(snapshot(), MATCH, "is")
    try:
        monitor.start()
        with qtbot.waitSignal(monitor.replace_finished, timeout=2000) as blocker:
            monitor.request_replace(request)
    finally:
        monitor.stop()
    assert replacer.requests == [request]
    assert blocker.args == expected


def test_check_now_emits_without_waiting_for_pause(qtbot):
    slow = Config(debounce_ms=10_000)
    monitor = TextMonitor(
        slow, reader=ScriptedReader(focus_result()), replacer=FakeReplacer(), poll_interval_s=FAST_POLL_S
    )
    try:
        monitor.start()
        with qtbot.waitSignal(monitor.text_ready, timeout=1000):
            monitor.request_check_now()
    finally:
        monitor.stop()


def test_short_text_is_not_checked_but_check_now_overrides(qtbot):
    one_word = focus_result(snapshot(text="teh"))
    monitor = TextMonitor(
        Config(debounce_ms=200, min_words=2),
        reader=ScriptedReader(one_word),
        replacer=FakeReplacer(),
        poll_interval_s=FAST_POLL_S,
    )
    ready = []
    monitor.text_ready.connect(ready.append)
    try:
        monitor.start()
        qtbot.wait(500)
        assert ready == []
        with qtbot.waitSignal(monitor.text_ready, timeout=1000):
            monitor.request_check_now()
    finally:
        monitor.stop()


def test_setup_hint_emitted_once_per_change(qtbot):
    from proofline.setup_hints import SetupHint
    from proofline.text_snapshot import FocusResult

    hint = SetupHint("google-docs", "Turn on screen reader support", "Press Ctrl+Alt+Z.")
    reader = ScriptedReader(FocusResult((1,), "msedge.exe Document", "read-only", None, hint))
    monitor = TextMonitor(FAST_CONFIG, reader=reader, replacer=FakeReplacer(), poll_interval_s=FAST_POLL_S)
    hints = []
    monitor.hint_available.connect(hints.append)
    try:
        monitor.start()
        qtbot.waitUntil(lambda: reader.calls > 10)
    finally:
        monitor.stop()
    assert hints == [hint]


def test_focus_changed_emitted_on_new_focus_or_status(qtbot, make_monitor):
    reader = ScriptedReader(focus_result())
    monitor = make_monitor(reader)
    seen = []
    monitor.focus_changed.connect(seen.append)
    monitor.start()
    qtbot.waitUntil(lambda: len(seen) == 1)
    reader.result = focus_result(None, reason="not a text control (ButtonControl)")
    qtbot.waitUntil(lambda: len(seen) == 2)
    qtbot.wait(50)
    assert len(seen) == 2  # no repeats while nothing changes


def _caret_monitor(reader, caret_reader):
    return TextMonitor(FAST_CONFIG, reader=reader, replacer=FakeReplacer(), poll_interval_s=FAST_POLL_S,
                       caret_reader=caret_reader)


def test_caret_offset_is_the_length_of_the_text_before_the_caret(qtbot):
    snap = snapshot(text="Hello there. Bye.")
    monitor = _caret_monitor(ScriptedReader(focus_result(snap)), lambda: "Hello th")
    try:
        monitor.start()
        with qtbot.waitSignal(monitor.caret_offset_ready, timeout=1000) as blocker:
            monitor.request_caret_offset()
    finally:
        monitor.stop()
    assert blocker.args == [snap, 8]


@pytest.mark.parametrize("before_caret", ["Something else", None])
def test_caret_text_that_does_not_match_gives_none(qtbot, before_caret):
    snap = snapshot(text="Hello there. Bye.")
    monitor = _caret_monitor(ScriptedReader(focus_result(snap)), lambda: before_caret)
    try:
        monitor.start()
        with qtbot.waitSignal(monitor.caret_offset_ready, timeout=1000) as blocker:
            monitor.request_caret_offset()
    finally:
        monitor.stop()
    assert blocker.args == [snap, None]


class FirstPollHasNoField:
    """No usable field on the first poll (password field, excluded app), a normal field after."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return focus_result(None, reason="skipped") if self.calls == 1 else focus_result()


def test_caret_request_without_a_field_is_dropped(qtbot):
    reader, caret_calls, emitted = FirstPollHasNoField(), [], []
    monitor = _caret_monitor(reader, lambda: caret_calls.append(1) or "This")
    monitor.caret_offset_ready.connect(lambda *args: emitted.append(args))
    monitor.request_caret_offset()  # pressed before the first poll, which finds no field
    try:
        monitor.start()
        qtbot.waitUntil(lambda: reader.calls >= 6, timeout=2000)
    finally:
        monitor.stop()
    assert emitted == [] and caret_calls == []


class FirstPollFails:
    """The first read raises (the element vanished); a normal field after."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("element went away")
        return focus_result()


def test_caret_request_is_dropped_when_the_read_fails(qtbot):
    reader, emitted = FirstPollFails(), []
    monitor = _caret_monitor(reader, lambda: "This")
    monitor.caret_offset_ready.connect(lambda *args: emitted.append(args))
    monitor.request_caret_offset()  # pressed before the first poll, whose read fails
    try:
        monitor.start()
        qtbot.waitUntil(lambda: reader.calls >= 6, timeout=2000)
    finally:
        monitor.stop()
    assert emitted == []
