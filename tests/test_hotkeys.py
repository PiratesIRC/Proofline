import ctypes

import pytest

from proofline.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    WM_HOTKEY,
    HotkeyError,
    HotkeyManager,
    parse_hotkey,
)

UNLIKELY_HOTKEY = "ctrl+alt+shift+f24"
TEST_ACTION = "test_action"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ctrl+alt+p", (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("P"))),
        ("Ctrl+Shift+F9", (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x78)),
        ("win+alt+space", (MOD_WIN | MOD_ALT | MOD_NOREPEAT, 0x20)),
        ("  CTRL + alt + 5 ", (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("5"))),
        ("ctrl+shift+enter", (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x0D)),
        ("alt+esc", (MOD_ALT | MOD_NOREPEAT, 0x1B)),
        ("ctrl+alt+f24", (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x87)),
    ],
)
def test_parse_hotkey_accepts_valid_text(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "p",  # no modifier
        "ctrl+alt",  # no key
        "ctrl+a+b",  # two keys
        "ctrl+",  # empty part
        "ctrl++p",  # empty part
        "",  # empty text
        "ctrl+f25",  # out of range function key
        "ctrl+ß",  # non-ASCII key
        "ctrl+bogus",  # unknown key name
    ],
)
def test_parse_hotkey_rejects_invalid_text(text):
    with pytest.raises(HotkeyError):
        parse_hotkey(text)


@pytest.fixture
def manager(qapp):
    widget = HotkeyManager()
    yield widget
    widget.unregister_all()
    widget.close()


def test_registered_hotkey_emits_triggered(qtbot, manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    hwnd = ctypes.c_void_p(int(manager.winId()))
    hotkey_id = manager._ids_by_name[TEST_ACTION]

    with qtbot.waitSignal(manager.triggered, timeout=2000) as blocker:
        ctypes.windll.user32.PostMessageW(hwnd, WM_HOTKEY, hotkey_id, 0)

    assert blocker.args == [TEST_ACTION]


def test_unknown_hotkey_id_emits_nothing(qtbot, manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    hwnd = ctypes.c_void_p(int(manager.winId()))

    with qtbot.assertNotEmitted(manager.triggered):
        ctypes.windll.user32.PostMessageW(hwnd, WM_HOTKEY, 9999, 0)
        qtbot.wait(50)


def test_unregister_all_frees_combination(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    manager.unregister_all()

    manager.register("other_action", UNLIKELY_HOTKEY)
    assert "other_action" in manager._ids_by_name


def test_taken_combination_raises(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    other = HotkeyManager()
    try:
        with pytest.raises(HotkeyError, match="already used"):
            other.register("other_action", UNLIKELY_HOTKEY)
    finally:
        other.close()


def test_reregistering_name_replaces_binding(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    manager.register(TEST_ACTION, "ctrl+alt+shift+f23")
    manager.register("other_action", UNLIKELY_HOTKEY)
    assert set(manager._ids_by_name) == {TEST_ACTION, "other_action"}


def test_empty_hotkey_unregisters_name(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    manager.register(TEST_ACTION, "  ")
    assert TEST_ACTION not in manager._ids_by_name


def test_invalid_hotkey_raises_and_keeps_existing_binding(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    with pytest.raises(HotkeyError):
        manager.register(TEST_ACTION, "not a hotkey")
    assert TEST_ACTION in manager._ids_by_name


def test_close_unregisters_everything(manager):
    manager.register(TEST_ACTION, UNLIKELY_HOTKEY)
    manager.close()
    assert not manager._ids_by_name
