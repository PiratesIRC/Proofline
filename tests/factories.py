import threading
from dataclasses import replace

from proofline.ai_client import AiResult
from proofline.ai_jobs import AI_CATEGORY, AI_RULE_ID, AI_SHORT_MESSAGE
from proofline.lt_client import Match
from proofline.text_snapshot import FieldSnapshot, FocusResult, ScreenRect

BASE_SNAPSHOT = FieldSnapshot(
    field_id=(42, 1),
    hwnd=0x1234,
    process_id=100,
    process_name="notepad.exe",
    window_title="notes.txt - Notepad",
    control_type="DocumentControl",
    class_name="RichEditD2DPT",
    text="This are a test.",
    field_rect=ScreenRect(0, 0, 400, 200),
    caret_rect=ScreenRect(10, 10, 11, 30),
    caret_source="uia-caret",
)


def snapshot(**changes):
    return replace(BASE_SNAPSHOT, **changes)


def focus_result(snap=BASE_SNAPSHOT, reason="ok via Text+Value"):
    key = snap.field_id if snap else (7,)
    return FocusResult(key, "notepad.exe DocumentControl", reason, snap)


class GatedBackend:
    """Answers in order, each only after gate.set(), so 'while it runs' is deterministic."""

    def __init__(self, *answers):
        self.answers, self.sent, self.gate = list(answers), [], threading.Event()

    def send(self, request, model):
        self.sent.append(request)
        assert self.gate.wait(5)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return AiResult(answer, 10, 5)


def finish(qtbot, r, signal_name="finished"):
    """Let r.backend answer and wait until r.service reports it."""
    with qtbot.waitSignal(getattr(r.service, signal_name)):
        r.backend.gate.set()


def issue(quote, occurrence=1, message="m", replacement="x"):
    """One finding as Claude returns it for Find more issues."""
    return {"quote": quote, "occurrence": occurrence, "message": message, "replacement": replacement}


def issue_match(quote, offset, replacement="x"):
    """An AI finding as Proofline builds it."""
    return Match(offset, len(quote), "m", AI_SHORT_MESSAGE, (replacement,), AI_RULE_ID, AI_CATEGORY, quote,
                 AI_CATEGORY)


def release_backends(backends):
    """Fixture teardown: let every waiting GatedBackend answer and wait for the pool threads.

    A worker still blocked on a gate at interpreter exit made pytest exit 127 after every test passed.
    """
    from PyQt6.QtCore import QThreadPool

    for backend in backends:
        backend.gate.set()
    QThreadPool.globalInstance().waitForDone(5000)
