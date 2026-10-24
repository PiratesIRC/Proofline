"""System-wide hotkeys via Win32 RegisterHotKey.

HotkeyManager is a hidden QWidget. Its native window receives WM_HOTKEY and
emits `triggered` with the action name. The owner should call unregister_all()
on quit; closing the manager also unregisters everything.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
NATIVE_EVENT_TYPE = b"windows_generic_MSG"

_MODIFIERS: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}
_NAMED_KEYS: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}
_VK_DIGIT_BASE = 0x30  # '0'..'9'
_VK_LETTER_BASE = 0x41  # 'A'..'Z'
_VK_F1 = 0x70
_MAX_FUNCTION_KEY = 24
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_DIGITS = frozenset("0123456789")
_SEPARATOR = "+"


# Qt key -> config name for the keys parse_hotkey() accepts besides letters, digits and F-keys.
_QT_KEY_NAMES = {
    "Key_Space": "space", "Key_Return": "enter", "Key_Enter": "enter", "Key_Tab": "tab",
    "Key_Escape": "esc", "Key_Backspace": "backspace", "Key_Delete": "delete", "Key_Insert": "insert",
    "Key_Home": "home", "Key_End": "end", "Key_PageUp": "pageup", "Key_PageDown": "pagedown",
}

def hotkey_from_key(key: object, modifiers: object) -> str | None:
    """A pressed Qt key plus modifiers in config form ("ctrl+alt+p"), or None if not usable.

    Needs at least one of Ctrl, Alt, Shift or Win plus one key parse_hotkey() understands.
    """
    from PyQt6.QtCore import Qt  # local: this module is otherwise free of Qt widgets

    mods = Qt.KeyboardModifier(modifiers)
    names = [name for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "ctrl"), (Qt.KeyboardModifier.AltModifier, "alt"),
        (Qt.KeyboardModifier.ShiftModifier, "shift"), (Qt.KeyboardModifier.MetaModifier, "win"),
    ) if mods & flag]
    key = Qt.Key(key)
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        name = chr(key.value).lower()
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key.value)
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        name = f"f{key.value - Qt.Key.Key_F1.value + 1}"
    else:
        name = _QT_KEY_NAMES.get(key.name, "")
    if not names or not name:
        return None
    return _SEPARATOR.join([*names, name])


def display_hotkey(value: str) -> str:
    """'ctrl+alt+p' as 'CTRL+ALT+P' for showing in Settings."""
    return value.upper()


class HotkeyError(ValueError):
    """Raised for an unparseable hotkey or one that cannot be registered."""


def parse_hotkey(text: str) -> tuple[int, int]:
    """Turn text such as 'ctrl+alt+p' into (modifiers, virtual_key).

    Requires at least one modifier and exactly one non-modifier key. The
    MOD_NOREPEAT flag is always included so holding the keys does not repeat.
    """
    parts = [part.strip().casefold() for part in text.split(_SEPARATOR)]
    if any(not part for part in parts):
        raise HotkeyError(f"'{text}' has an empty part; use the form ctrl+alt+p.")

    modifiers = 0
    keys: list[str] = []
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        else:
            keys.append(part)

    if not modifiers:
        raise HotkeyError(
            f"'{text}' needs at least one modifier (ctrl, alt, shift or win)."
        )
    if len(keys) != 1:
        raise HotkeyError(f"'{text}' must have exactly one key besides the modifiers.")
    return modifiers | MOD_NOREPEAT, _virtual_key(keys[0], text)


def _virtual_key(key: str, text: str) -> int:
    """Map one key name to a Win32 virtual-key code."""
    if len(key) == 1 and key in _ASCII_LETTERS:
        return _VK_LETTER_BASE + ord(key) - ord("a")
    if len(key) == 1 and key in _ASCII_DIGITS:
        return _VK_DIGIT_BASE + int(key)
    if key in _NAMED_KEYS:
        return _NAMED_KEYS[key]
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= _MAX_FUNCTION_KEY:
            return _VK_F1 + number - 1
    raise HotkeyError(f"'{text}' has an unknown key '{key}'.")


def _user32() -> ctypes.WinDLL:
    return ctypes.windll.user32  # type: ignore[attr-defined]


class HotkeyManager(QWidget):
    """Owns a set of named global hotkeys bound to this widget's native window."""

    triggered = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._ids_by_name: dict[str, int] = {}
        self._names_by_id: dict[int, str] = {}
        self._next_id = 1

    def register(self, name: str, hotkey: str) -> None:
        """Bind hotkey to name, replacing any previous binding for name.

        An empty hotkey only removes the existing binding. Raises HotkeyError if
        the text is invalid or another app already owns the combination.
        """
        if not hotkey.strip():
            self._unbind(name)
            return
        modifiers, virtual_key = parse_hotkey(hotkey)
        self._unbind(name)
        hotkey_id = self._allocate_id(name)
        hwnd = ctypes.c_void_p(int(self.winId()))
        if not _user32().RegisterHotKey(hwnd, hotkey_id, modifiers, virtual_key):
            self._forget(name, hotkey_id)
            raise HotkeyError(f"The hotkey '{hotkey}' is already used by another app.")
        log.info("Registered hotkey for %s", name)

    def unregister_all(self) -> None:
        """Release every hotkey this manager registered."""
        for name in list(self._ids_by_name):
            self._unbind(name)

    def close(self) -> bool:
        self.unregister_all()
        return super().close()

    def closeEvent(self, event) -> None:
        self.unregister_all()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        """Handle WM_HOTKEY; let Qt process everything else.

        Unhandled messages return (False, 0) rather than super()'s result: under
        PyQt6 that result carries a None which crashes Qt when it is read back.
        """
        if bytes(event_type) == NATIVE_EVENT_TYPE and int(message):
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                name = self._names_by_id.get(int(msg.wParam))
                if name is not None:
                    self.triggered.emit(name)
                return True, 0
        return False, 0

    def _allocate_id(self, name: str) -> int:
        hotkey_id = self._next_id
        self._next_id += 1
        self._ids_by_name[name] = hotkey_id
        self._names_by_id[hotkey_id] = name
        return hotkey_id

    def _forget(self, name: str, hotkey_id: int) -> None:
        self._ids_by_name.pop(name, None)
        self._names_by_id.pop(hotkey_id, None)

    def _unbind(self, name: str) -> None:
        hotkey_id = self._ids_by_name.get(name)
        if hotkey_id is None:
            return
        hwnd = ctypes.c_void_p(int(self.winId()))
        _user32().UnregisterHotKey(hwnd, hotkey_id)
        self._forget(name, hotkey_id)
