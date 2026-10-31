from dataclasses import replace

import pytest
from factories import focus_result, snapshot
from PyQt6.QtGui import QGuiApplication

from proofline.config import Config, ConfigError, field_signature, save_config
from proofline.field_picker import FieldPickerDialog, assess, details_text
from proofline.setup_hints import SetupHint
from proofline.text_monitor import TextMonitor
from proofline.text_snapshot import FocusResult

SIG = field_signature("erp.exe", "PaneControl", "TEditor")


def captured(reason, patterns="Text+Value", process="erp.exe", title="Orders - ERP", snap=None, hint=None):
    return FocusResult((9,), "erp.exe PaneControl", reason, snap, hint, process, title, SIG, patterns)


@pytest.mark.parametrize(
    ("result", "verdict", "add_field", "add_app"),
    [
        (captured("ok via Text+Value", snap=snapshot()), "Already checked ✓", False, False),
        (captured("not a text control (PaneControl)"), "Skipped by a rule", True, False),
        (captured("address bar"), "Skipped by a rule", True, False),
        (captured("sensitive field (card number)"), "Skipped by a rule", True, False),
        (captured("not a text control (PaneControl)", patterns="none"), "Text isn't available", False, False),
        (captured("password field"), "Password field", False, False),
        (captured("read-only"), "Read-only", False, False),
        (captured("app runs as administrator; Windows blocks it"), "Can't read this app", False, False),
        (captured("UIA error: gone"), "Not supported", False, False),
    ],
)
def test_assess_verdicts(result, verdict, add_field, add_app):
    assessment = assess(result, Config())
    assert (assessment.verdict, assessment.can_add_field, assessment.can_add_app) == (verdict, add_field, add_app)


def test_assess_excluded_text_box_offers_always_check_app():
    result = captured("ok via Text", process="mstsc.exe", snap=snapshot())
    assessment = assess(result, Config())  # mstsc.exe is excluded by default
    assert assessment.verdict == "Turned off here"
    assert assessment.can_add_app


def test_assess_includes_setup_hint_when_text_unavailable():
    hint = SetupHint("google-docs", "Docs", "Press Ctrl+Alt+Z.")
    assessment = assess(captured("no Text or Value pattern", patterns="none", hint=hint), Config())
    assert "Ctrl+Alt+Z" in assessment.explanation


@pytest.mark.parametrize("reason", ["focus is in this app", "no focused element", "checking paused"])
def test_assess_ignores_own_window_and_nothing(reason):
    assert assess(captured(reason), Config()) is None


def test_details_text_has_signature_but_no_field_text():
    text = details_text(captured("not a text control (PaneControl)", snap=snapshot(text="secret words")))
    assert SIG in text
    assert "secret" not in text


@pytest.fixture
def dialog(qtbot):
    d = FieldPickerDialog(lambda: Config())
    qtbot.addWidget(d)
    return d


def test_dialog_starts_and_stops_capture(qtbot, dialog):
    with qtbot.waitSignal(dialog.capture_started):
        dialog.open_picker()
    with qtbot.waitSignal(dialog.capture_stopped):
        dialog.close()


def test_dialog_ignores_own_window_and_enables_right_buttons(qtbot, dialog):
    dialog.open_picker()
    dialog.on_captured(captured("focus is in this app"))
    assert not dialog._copy_button.isEnabled()
    dialog.on_captured(captured("not a text control (PaneControl)"))
    assert dialog._add_field_button.isEnabled()
    assert not dialog._add_app_button.isEnabled()
    with qtbot.waitSignal(dialog.add_field_requested) as blocker:
        dialog._add_field_button.click()
    assert blocker.args == [SIG]
    assert dialog._verdict.text() == "Added ✓"
    assert not dialog._add_field_button.isEnabled()


@pytest.mark.clipboard
def test_dialog_copy_details(dialog):
    dialog.on_captured(captured("read-only"))
    dialog._copy_button.click()
    assert SIG in QGuiApplication.clipboard().text()


def test_custom_field_signatures_validated(tmp_path):
    saved = save_config(Config(custom_fields=(SIG,)), tmp_path / "c.json")
    assert saved.is_custom_field(SIG.upper())
    for bad in ("erp.exe", "erp.exe|PaneControl", "|PaneControl|X", "a|b|c|d"):
        with pytest.raises(ConfigError):
            save_config(Config(custom_fields=(bad,)), tmp_path / "c.json")


def test_always_check_apps_override_exclusions():
    config = Config(always_check_apps=("MSTSC.exe",))
    assert not config.is_disabled_for("mstsc.exe", "server - Remote Desktop Connection")


class Reader:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.result


def test_capture_reports_even_when_paused_and_excluded(qtbot):
    reader = Reader(captured("ok via Text", process="mstsc.exe", snap=snapshot(process_name="mstsc.exe")))
    monitor = TextMonitor(Config(enabled=False), reader=reader, replacer=lambda r: None, poll_interval_s=0.01)
    try:
        monitor.start()
        qtbot.wait(100)
        assert reader.calls == 0  # paused and not capturing: nothing is read
        with qtbot.waitSignal(monitor.captured, timeout=1000) as blocker:
            monitor.start_capture()
        assert blocker.args[0].process_name == "mstsc.exe"
    finally:
        monitor.stop()


def test_custom_field_bypasses_exclusions_in_monitor(qtbot):
    snap = snapshot(process_name="mstsc.exe")
    result = replace(focus_result(snap), signature=SIG)
    monitor = TextMonitor(
        Config(debounce_ms=200, custom_fields=(SIG,)), reader=Reader(result), replacer=lambda r: None,
        poll_interval_s=0.01,
    )
    try:
        with qtbot.waitSignal(monitor.text_ready, timeout=2000):
            monitor.start()
    finally:
        monitor.stop()


def test_wildcard_class_matches_any_class_and_web_classes_saved_as_wildcard():
    from proofline.config import custom_field_matches, saveable_signature

    web = "msedgewebview2.exe|EditControl|fui-Primitive ___1czdayc ck-focused"
    assert saveable_signature(web) == "msedgewebview2.exe|EditControl|*"
    assert saveable_signature(SIG) == SIG  # simple class names are kept
    entries = ("msedgewebview2.exe|EditControl|*",)
    assert custom_field_matches(web, entries)
    assert custom_field_matches("MSEDGEWEBVIEW2.EXE|EditControl|other", entries)
    assert not custom_field_matches("msedgewebview2.exe|DocumentControl|x", entries)


def test_only_relevant_buttons_show_and_details_start_folded(qtbot, dialog):
    dialog.open_picker()
    assert not dialog._add_field_button.isVisibleTo(dialog) and not dialog._add_app_button.isVisibleTo(dialog)
    assert not dialog._details.isVisibleTo(dialog)
    dialog.on_captured(captured("not a text control (PaneControl)"))
    assert dialog._add_field_button.isVisibleTo(dialog) and not dialog._add_app_button.isVisibleTo(dialog)
    dialog._details_toggle.click()
    assert dialog._details.isVisibleTo(dialog) and dialog._copy_button.isVisibleTo(dialog)
    assert dialog.objectName() == "uiRoot"  # styled like the rest of the app
