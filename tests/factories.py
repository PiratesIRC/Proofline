from dataclasses import replace

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
