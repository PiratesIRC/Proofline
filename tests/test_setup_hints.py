"""Tests for proofline.setup_hints: which one-time setup tips apply to a window."""

from __future__ import annotations

import sys

import pytest

from proofline import setup_hints
from proofline.setup_hints import (
    HINT_KEYS,
    SetupHint,
    firefox_major_version,
    hint_for,
    unseen,
)

DOCS_TITLE = "Quarterly plan - Google Docs - Microsoft Edge"


def _hint(
    process: str = "",
    title: str = "",
    class_name: str = "",
    is_text_field: bool = False,
    exe_path: str = "",
) -> SetupHint | None:
    return hint_for(process, title, "", class_name, is_text_field, exe_path)


def _set_firefox_version(monkeypatch: pytest.MonkeyPatch, version: int | None) -> None:
    monkeypatch.setattr(setup_hints, "firefox_major_version", lambda _path: version)


@pytest.mark.parametrize(
    "process",
    ["msedge.exe", "chrome.exe", "vivaldi.exe", "brave.exe", "firefox.exe", "opera.exe"],
)
def test_google_docs_hint_in_browsers(process: str) -> None:
    hint = _hint(process=process, title=DOCS_TITLE)
    assert hint is not None
    assert hint.key == "google-docs"
    assert "Ctrl+Alt+Z" in hint.message


@pytest.mark.parametrize("process", ["MSEDGE.EXE", "Chrome.exe"])
def test_google_docs_process_match_is_case_insensitive(process: str) -> None:
    hint = _hint(process=process, title=DOCS_TITLE)
    assert hint is not None
    assert hint.key == "google-docs"


@pytest.mark.parametrize(
    "title",
    ["Google Docs", "Notes – Google Docs", "Document - Google Docs"],
)
def test_google_docs_title_fallback(title: str) -> None:
    hint = _hint(process="msedge.exe", title=title)
    assert hint is not None
    assert hint.key == "google-docs"


def test_non_browser_with_google_docs_title_gets_no_hint() -> None:
    assert _hint(process="notepad.exe", title=DOCS_TITLE) is None


@pytest.mark.parametrize(
    "process_name, class_name",
    [("javaw.exe", "Frame"), ("java.exe", "Frame"), ("other.exe", "SunAwtFrame")],
)
def test_java_hint_by_process_or_class(process_name: str, class_name: str) -> None:
    hint = _hint(process=process_name, class_name=class_name)
    assert hint is not None
    assert hint.key == "java-access-bridge"
    assert "jabswitch -enable" in hint.message


@pytest.mark.parametrize("class_name", ["SunAwtCanvas", "SunAwtDialog"])
def test_java_hint_by_awt_class_prefix(class_name: str) -> None:
    hint = _hint(process="myapp.exe", class_name=class_name)
    assert hint is not None
    assert hint.key == "java-access-bridge"


def test_unrelated_app_gets_no_hint() -> None:
    assert _hint(process="notepad.exe", class_name="Edit", title="Untitled") is None


def test_firefox_below_143_gets_update_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_firefox_version(monkeypatch, 142)
    hint = _hint(process="firefox.exe", exe_path=r"C:\Firefox\firefox.exe")
    assert hint is not None
    assert hint.key == "firefox-update"
    assert "143" in hint.message


def test_firefox_at_143_gets_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_firefox_version(monkeypatch, 143)
    assert _hint(process="firefox.exe", exe_path=r"C:\Firefox\firefox.exe") is None


def test_firefox_unknown_version_gets_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_firefox_version(monkeypatch, None)
    assert _hint(process="firefox.exe", exe_path=r"C:\Firefox\firefox.exe") is None


def test_firefox_without_exe_path_gets_no_hint() -> None:
    assert _hint(process="firefox.exe", exe_path="") is None


@pytest.mark.parametrize(
    "process, title, class_name",
    [
        ("msedge.exe", DOCS_TITLE, ""),
        ("javaw.exe", "IDE", "SunAwtFrame"),
        ("firefox.exe", "Old Firefox", ""),
    ],
)
def test_text_field_suppresses_every_hint(
    monkeypatch: pytest.MonkeyPatch, process: str, title: str, class_name: str
) -> None:
    _set_firefox_version(monkeypatch, 100)
    assert _hint(process=process, title=title, class_name=class_name) is not None
    assert (
        _hint(process=process, title=title, class_name=class_name, is_text_field=True)
        is None
    )


def test_firefox_major_version_reads_real_file() -> None:
    version = firefox_major_version(sys.executable)
    assert isinstance(version, int)
    assert version > 0


@pytest.mark.parametrize("path", ["", r"C:\does\not\exist\firefox.exe"])
def test_firefox_major_version_returns_none_on_failure(path: str) -> None:
    assert firefox_major_version(path) is None


def test_unseen_returns_hint_when_key_not_shown() -> None:
    hint = SetupHint(key="google-docs", title="t", message="m")
    assert unseen(hint, ["java-access-bridge"]) is hint


def test_unseen_filters_shown_hint() -> None:
    hint = SetupHint(key="google-docs", title="t", message="m")
    assert unseen(hint, ["google-docs"]) is None


def test_unseen_passes_none_through() -> None:
    assert unseen(None, []) is None


def test_unseen_accepts_generator() -> None:
    hint = SetupHint(key="firefox-update", title="t", message="m")
    assert unseen(hint, (key for key in HINT_KEYS if key != "firefox-update")) is hint


def test_hint_keys_cover_every_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_firefox_version(monkeypatch, 100)
    produced = {
        _hint(process="msedge.exe", title=DOCS_TITLE),
        _hint(process="javaw.exe"),
        _hint(process="firefox.exe"),
    }
    assert {hint.key for hint in produced if hint is not None} == set(HINT_KEYS)


@pytest.mark.parametrize("key", ["google-docs", "java-access-bridge", "firefox-update"])
def test_tip_text_has_no_raw_urls_or_markdown(key):
    from proofline import setup_hints

    hint = {"google-docs": setup_hints._google_docs_hint("chrome.exe", "Doc - Google Docs"),
            "java-access-bridge": setup_hints._java_hint("javaw.exe", ""),
            "firefox-update": setup_hints.SetupHint(setup_hints.KEY_FIREFOX_UPDATE, "", setup_hints.FIREFOX_MESSAGE,
                                                    setup_hints.FIREFOX_URL)}[key]
    assert "http" not in hint.message and "`" not in hint.message
    assert hint.url.startswith("https://")
