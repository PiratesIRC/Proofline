"""One-time setup tips for apps whose text needs a setting turned on before it can be read.

Some apps (Google Docs in a browser, Java Swing/AWT, older Firefox) expose no readable
text through UI Automation until the user changes a setting. These rules look at the
focused window and suggest that change. The caller persists which tips were shown;
this module only decides.

Only `firefox_major_version` touches Windows (through pywin32); the rest is pure logic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import pywintypes
import win32api

logger = logging.getLogger(__name__)

KEY_GOOGLE_DOCS = "google-docs"
KEY_JAVA_ACCESS_BRIDGE = "java-access-bridge"
KEY_FIREFOX_UPDATE = "firefox-update"
HINT_KEYS: tuple[str, ...] = (
    KEY_GOOGLE_DOCS,
    KEY_JAVA_ACCESS_BRIDGE,
    KEY_FIREFOX_UPDATE,
)

BROWSER_PROCESSES: frozenset[str] = frozenset(
    {"msedge.exe", "chrome.exe", "vivaldi.exe", "brave.exe", "firefox.exe", "opera.exe"}
)
JAVA_PROCESSES: frozenset[str] = frozenset({"java.exe", "javaw.exe"})
FIREFOX_PROCESS = "firefox.exe"
JAVA_CLASS_PREFIX = "SunAwt"
GOOGLE_DOCS_TITLE_MARKER = "Google Docs"

# Firefox gained UI Automation support in this major version.
FIREFOX_UIA_MIN_MAJOR = 143
VERSION_INFO_ROOT = "\\"
FILE_VERSION_MS_KEY = "FileVersionMS"
VERSION_MAJOR_SHIFT = 16

GOOGLE_DOCS_URL = "https://support.google.com/docs/answer/6282736"
JAVA_ACCESS_BRIDGE_URL = (
    "https://docs.oracle.com/en/java/javase/21/docs/specs/man/jabswitch.html"
)


@dataclass(frozen=True)
class SetupHint:
    """A one-time tip telling the user how to make an app's text readable."""

    key: str
    title: str
    message: str


def hint_for(
    process_name: str,
    window_title: str,
    framework_id: str,
    class_name: str,
    is_text_field: bool,
    exe_path: str = "",
) -> SetupHint | None:
    """Return the setup tip for the focused window, or None if no tip applies.

    A real editable text field never gets a tip, because its text is already readable.
    """
    if is_text_field:
        return None
    process = process_name.lower()
    return (
        _google_docs_hint(process, window_title)
        or _java_hint(process, class_name)
        or _firefox_hint(process, exe_path)
    )


def firefox_major_version(exe_path: str) -> int | None:
    """Return Firefox's major version from its executable's file version, or None."""
    if not exe_path:
        return None
    try:
        info = win32api.GetFileVersionInfo(exe_path, VERSION_INFO_ROOT)
    except pywintypes.error as exc:
        logger.debug("Could not read file version of %s: %s", exe_path, exc)
        return None
    version_ms = info.get(FILE_VERSION_MS_KEY)
    if version_ms is None:
        return None
    return version_ms >> VERSION_MAJOR_SHIFT


def unseen(hint: SetupHint | None, shown_keys: Iterable[str]) -> SetupHint | None:
    """Return the hint only if the user has not already been shown it."""
    if hint is None:
        return None
    shown = frozenset(shown_keys)
    return None if hint.key in shown else hint


def _google_docs_hint(process: str, window_title: str) -> SetupHint | None:
    if process not in BROWSER_PROCESSES or GOOGLE_DOCS_TITLE_MARKER not in window_title:
        return None
    return SetupHint(
        key=KEY_GOOGLE_DOCS,
        title="Turn on screen reader support in Google Docs",
        message=(
            "In the document, press Ctrl+Alt+Z, or choose Tools > Accessibility > "
            "Turn on screen reader support. "
            f"More details: {GOOGLE_DOCS_URL}"
        ),
    )


def _java_hint(process: str, class_name: str) -> SetupHint | None:
    if process not in JAVA_PROCESSES and not class_name.startswith(JAVA_CLASS_PREFIX):
        return None
    return SetupHint(
        key=KEY_JAVA_ACCESS_BRIDGE,
        title="Turn on Java Access Bridge",
        message=(
            "Open Command Prompt, run `jabswitch -enable`, then restart the Java app. "
            f"More details: {JAVA_ACCESS_BRIDGE_URL}"
        ),
    )


def _firefox_hint(process: str, exe_path: str) -> SetupHint | None:
    if process != FIREFOX_PROCESS:
        return None
    version = firefox_major_version(exe_path)
    if version is None or version >= FIREFOX_UIA_MIN_MAJOR:
        return None
    return SetupHint(
        key=KEY_FIREFOX_UPDATE,
        title="Update Firefox",
        message=(
            "This Firefox version cannot expose text to the grammar checker. "
            f"Update Firefox to version {FIREFOX_UIA_MIN_MAJOR} or newer, "
            "then restart it."
        ),
    )
