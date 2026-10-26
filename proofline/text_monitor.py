"""Background thread that watches the focused text field and detects typing pauses."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from proofline.config import Config
from proofline.replace_request import ReplaceError, ReplaceRequest
from proofline.text_snapshot import (
    FieldSnapshot,
    FocusResult,
    TypingDebouncer,
    loggable,
    word_count,
)
from proofline.underlines import Underlines, UnderlineTarget

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.3
STOP_TIMEOUT_MS = 3000
ERROR_LOG_EVERY = 50
MS_PER_S = 1000

Reader = Callable[[], FocusResult]
PAUSED = FocusResult((), "", "checking paused")
Replacer = Callable[[ReplaceRequest], None]
RectReader = Callable[[UnderlineTarget], Underlines | None]
CaretReader = Callable[[], str | None]  # the field's text from its start to the caret


def _no_caret() -> str | None:
    return None


def _no_rects(_target: UnderlineTarget) -> Underlines | None:
    return None


class TextMonitor(QThread):
    """Polls the focused element and reports what it finds.

    field_changed(FieldSnapshot | None): focus moved, or text/caret changed.
    text_ready(FieldSnapshot): the text has been unchanged for config.debounce_ms.
    replace_finished(bool, str): outcome of request_replace(); the message explains failures.
    underlines_changed(Underlines | None): where the set_underline_target() spans sit on
        screen, re-measured every poll (scrolling moves them without changing the text).

    All UI Automation work happens on this thread; pass `reader` and `replacer` to
    substitute fakes in tests.
    """

    field_changed = pyqtSignal(object)
    text_ready = pyqtSignal(object)
    hint_available = pyqtSignal(object)  # setup_hints.SetupHint for the focused app
    captured = pyqtSignal(object)  # FocusResult before exclusions, while capture is on
    focus_changed = pyqtSignal(object)  # FocusResult whenever the focused element or its status changes
    replace_finished = pyqtSignal(bool, str)
    underlines_changed = pyqtSignal(object)
    caret_offset_ready = pyqtSignal(object, object)  # FieldSnapshot, caret offset (int) or None

    def __init__(
        self,
        config: Config,
        reader: Reader | None = None,
        replacer: Replacer | None = None,
        clock: Callable[[], float] = time.monotonic,
        poll_interval_s: float = POLL_INTERVAL_S,
        rect_reader: RectReader | None = None,
        caret_reader: CaretReader | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("TextMonitor")
        self._config = config
        self._reader = reader
        self._replacer = replacer
        self._rect_reader = rect_reader
        self._caret_reader = caret_reader
        self._underline_target: UnderlineTarget | None = None
        self._requests: queue.SimpleQueue[ReplaceRequest] = queue.SimpleQueue()
        self._clock = clock
        self._poll_interval_s = poll_interval_s
        self._stop_event = threading.Event()
        self._check_now = threading.Event()
        self._caret_wanted = threading.Event()
        self._capture = threading.Event()

    def set_config(self, config: Config) -> None:
        # Config is immutable, so swapping the reference is thread-safe.
        self._config = config

    def request_replace(self, request: ReplaceRequest) -> None:
        """Queue a correction; it is applied on the monitor thread before the next poll."""
        self._requests.put(request)

    def set_underline_target(self, target: UnderlineTarget | None) -> None:
        """Spans to measure while the field holds target.text; None stops measuring."""
        self._underline_target = target  # immutable, so swapping the reference is thread-safe

    def start_capture(self) -> None:
        """Report every focus change via `captured`, even when paused or excluded."""
        self._capture.set()

    def stop_capture(self) -> None:
        self._capture.clear()

    def request_check_now(self) -> None:
        """Check the focused field on the next poll without waiting for a typing pause."""
        self._check_now.set()

    def request_caret_offset(self) -> None:
        """Emit caret_offset_ready on the next poll if it finds a field; dropped otherwise."""
        self._caret_wanted.set()

    def stop(self) -> None:
        self._stop_event.set()
        if not self.wait(STOP_TIMEOUT_MS):
            log.warning("Text monitor did not stop within %d ms", STOP_TIMEOUT_MS)

    def run(self) -> None:
        threading.current_thread().name = "TextMonitor"
        if self._reader is not None and self._replacer is not None:
            self._loop(self._reader, self._replacer, self._rect_reader or _no_rects,
                       self._caret_reader or _no_caret)
            return
        # Imported here so UIA and its COM apartment belong to this thread.
        import uiautomation as auto

        from proofline import text_replace, uia_reader, underline_rects

        with auto.UIAutomationInitializerInThread():
            self._loop(
                self._reader
                or (
                    lambda: uia_reader.read_focused_field(
                        self._config.custom_fields, diagnose=self._capture.is_set()
                    )
                ),
                self._replacer or text_replace.replace_in_focused_field,
                self._rect_reader or underline_rects.measure,
                self._caret_reader or uia_reader.read_text_before_caret,
            )

    def _report_capture(
        self, raw: FocusResult, last: tuple[object, ...] | None
    ) -> tuple[object, ...]:
        """Emit `captured` when the focused element or what we know about it changes."""
        key = (raw.focus_key, raw.reason, raw.patterns)
        if key != last:
            self.captured.emit(raw)
        return key

    def _apply_pending_replacements(self, replacer: Replacer) -> None:
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            try:
                replacer(request)
            except ReplaceError as exc:
                log.warning("Correction not applied: %s", exc)
                self.replace_finished.emit(False, str(exc))
            except Exception:  # the monitor must survive any replacer failure
                log.exception("Unexpected error while applying a correction")
                self.replace_finished.emit(False, "Unexpected error; see the log for details.")
            else:
                self.replace_finished.emit(True, "")

    def _measure_underlines(
        self, snapshot: FieldSnapshot | None, rect_reader: RectReader, last: Underlines | None
    ) -> Underlines | None:
        """Emit underlines_changed when the measured rectangles differ from the last poll."""
        target = self._underline_target
        underlines = None
        if target is not None and target.applies_to(snapshot):
            try:
                underlines = rect_reader(target)
            except Exception:  # elements vanish mid-measure; the next poll tries again
                log.debug("Measuring underlines failed", exc_info=True)
        if underlines != last:
            self.underlines_changed.emit(underlines)
        return underlines

    def _report_caret(self, snapshot: FieldSnapshot | None, caret_reader: CaretReader) -> None:
        """Answer a caret request on this poll only: a press where no field is read is dropped."""
        if not self._caret_wanted.is_set():
            return
        self._caret_wanted.clear()
        if snapshot is None:
            return
        try:
            before = caret_reader()
        except Exception:  # elements vanish; the card then says it cannot find the caret
            log.debug("Reading the caret position failed", exc_info=True)
            before = None
        offset = len(before) if before is not None and snapshot.text.startswith(before) else None
        self.caret_offset_ready.emit(snapshot, offset)

    def _loop(self, reader: Reader, replacer: Replacer, rect_reader: RectReader, caret_reader: CaretReader) -> None:
        log.info("Text monitor running (poll every %.0f ms)", self._poll_interval_s * MS_PER_S)
        delay_ms = self._config.debounce_ms
        debouncer = TypingDebouncer(delay_ms / MS_PER_S)
        previous: FocusResult | None = None
        failures = 0
        last_captured: tuple[object, ...] | None = None
        underlines: Underlines | None = None

        while not self._stop_event.wait(self._poll_interval_s):
            self._apply_pending_replacements(replacer)
            config = self._config
            if config.debounce_ms != delay_ms:
                delay_ms = config.debounce_ms
                debouncer = TypingDebouncer(delay_ms / MS_PER_S)
            capturing = self._capture.is_set()
            try:
                raw = reader() if config.enabled or capturing else PAUSED
                result = _apply_config(raw, config)
            except Exception:  # the monitor must survive any reader failure
                self._caret_wanted.clear()  # a shortcut press is answered on this poll or dropped
                failures += 1
                if failures % ERROR_LOG_EVERY == 1:
                    log.exception("Reading the focused field failed (%d failures so far)", failures)
                continue

            last_captured = self._report_capture(raw, last_captured) if capturing else None
            _log_change(previous, result)
            if previous is None or (previous.focus_key, previous.reason) != (result.focus_key, result.reason):
                self.focus_changed.emit(result)
            if result.hint is not None and (previous is None or previous.hint != result.hint):
                self.hint_available.emit(result.hint)
            if previous is None or result.snapshot != previous.snapshot:
                self.field_changed.emit(result.snapshot)
            previous = result
            self._report_caret(result.snapshot, caret_reader)
            underlines = self._measure_underlines(result.snapshot, rect_reader, underlines)

            ready = debouncer.update(result.snapshot, self._clock())
            if ready is not None and word_count(ready.text) < config.min_words:
                log.debug("Skipping check: fewer than %d words", config.min_words)
                ready = None
            if self._check_now.is_set():  # explicit request: ignore pause and minimum length
                self._check_now.clear()
                ready = result.snapshot or ready
            if ready is not None:
                log.info("Typing paused in %s: %s", ready.describe(), loggable(ready.text))
                self.text_ready.emit(ready)
        log.info("Text monitor stopped")


def _apply_config(result: FocusResult, config: Config) -> FocusResult:
    if not config.enabled:
        return PAUSED
    snapshot = result.snapshot
    excluded = snapshot and config.is_disabled_for(snapshot.process_name, snapshot.window_title)
    if excluded and not config.is_custom_field(result.signature):
        return FocusResult(result.focus_key, result.description, "disabled for this app/window")
    return result


def _log_change(previous: FocusResult | None, current: FocusResult) -> None:
    if (
        previous is None
        or previous.focus_key != current.focus_key
        or previous.reason != current.reason
    ):
        log.info("Focus: %s -> %s", current.description or "-", current.reason)
    snapshot = current.snapshot
    old = previous.snapshot if previous else None
    if snapshot and (old is None or old.caret_source != snapshot.caret_source):
        log.debug(
            "Caret via %s at %s; field %s; window %r",
            snapshot.caret_source,
            snapshot.caret_rect,
            snapshot.field_rect,
            snapshot.window_title,
        )
