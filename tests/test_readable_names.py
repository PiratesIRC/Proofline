"""Settings show readable names instead of raw IDs (UI review item 4)."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from proofline.app_names import running_apps
from proofline.config import Config, rule_label, with_rule_label
from proofline.hotkeys import display_hotkey, hotkey_from_key
from proofline.list_editor import StringListEditor
from proofline.settings_pages import (
    CategoryChecklist,
    HotkeyRecorder,
    custom_field_label,
)


def test_list_editor_shows_labels_but_keeps_values(qtbot):
    editor = StringListEditor("", "", label=lambda value: f"Label for {value}")
    qtbot.addWidget(editor)
    editor.set_items(("A", "B"))
    assert editor.items() == ("A", "B")
    assert editor._list.item(0).text() == "Label for A"
    editor.add_item("C")
    assert editor.items() == ("A", "B", "C") and editor._list.item(2).text() == "Label for C"


def test_rule_labels_are_recorded_and_looked_up():
    config = with_rule_label(Config(), "MORFOLOGIK_RULE_EN_US", "Possible spelling mistake")
    assert rule_label(config, "MORFOLOGIK_RULE_EN_US") == "Possible spelling mistake (MORFOLOGIK_RULE_EN_US)"
    assert rule_label(config, "TYPED_BY_HAND") == "TYPED_BY_HAND"
    again = with_rule_label(config, "MORFOLOGIK_RULE_EN_US", "Spelling")
    assert again.rule_labels == ("MORFOLOGIK_RULE_EN_US=Spelling",)  # one entry per rule, latest wins


def test_category_checklist_names_categories_and_keeps_unknown_ones(qtbot):
    checklist = CategoryChecklist()
    qtbot.addWidget(checklist)
    checklist.set_disabled(("STYLE", "SOMETHING_NEW"))
    assert checklist.box("STYLE").text() == "Style" and checklist.box("STYLE").isChecked()
    assert checklist.box("SOMETHING_NEW").isChecked()  # unknown ones stay visible and turned off
    with qtbot.waitSignal(checklist.changed):
        checklist.box("TYPOS").click()
    assert set(checklist.disabled()) == {"STYLE", "SOMETHING_NEW", "TYPOS"}


def test_custom_field_label_reads_like_a_sentence():
    assert custom_field_label("notepad.exe|DocumentControl|RichEditD2DPT") == "notepad.exe: DocumentControl (RichEditD2DPT)"
    assert custom_field_label("odd entry") == "odd entry"


def test_running_apps_lists_each_windowed_app_once_by_name():
    windows = [(10, "Untitled - Notepad"), (10, "Other - Notepad"), (20, "Inbox"), (30, ""), (99, "Proofline")]
    paths = {10: r"C:\Windows\notepad.exe", 20: r"C:\Apps\mail.exe", 30: r"C:\Apps\hidden.exe", 99: r"C:\x\Proofline.exe"}
    names = {r"C:\Windows\notepad.exe": "Notepad", r"C:\Apps\mail.exe": ""}
    apps = running_apps(windows=lambda: windows, path_of=paths.get, describe=lambda p: names.get(p, ""), own_pid=99)
    assert apps == [("mail.exe", "mail.exe"), ("notepad.exe", "Notepad")]


@pytest.mark.parametrize(("key", "mods", "expected"), [
    (Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier, "ctrl+alt+p"),
    (Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier, "shift+f5"),
    (Qt.Key.Key_PageUp, Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier, "ctrl+win+pageup"),
    (Qt.Key.Key_7, Qt.KeyboardModifier.ControlModifier, "ctrl+7"),
    (Qt.Key.Key_P, Qt.KeyboardModifier.NoModifier, None),  # needs a modifier
    (Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier, None),  # a modifier alone
])
def test_hotkey_from_key(key, mods, expected):
    assert hotkey_from_key(key, mods) == expected


def test_display_hotkey():
    assert display_hotkey("ctrl+alt+p") == "CTRL+ALT+P"
    assert display_hotkey("win+shift+pageup") == "WIN+SHIFT+PAGEUP"
    assert display_hotkey("") == ""


def test_recorder_records_a_pressed_combination(qtbot):
    recorder = HotkeyRecorder()
    qtbot.addWidget(recorder)
    recorder.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_K,
                                     Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier))
    assert recorder.hotkey() == "ctrl+alt+k" and recorder.text() == "CTRL+ALT+K"
    recorder.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier))
    assert recorder.hotkey() == ""  # Backspace alone clears it (shortcut off)


# Category ids defined in LanguageTool's Categories.java (measured 2026-10-24 from the master branch).
LANGUAGETOOL_CATEGORIES = {
    "CASING", "COMPOUNDING", "GRAMMAR", "TYPOS", "PUNCTUATION", "TYPOGRAPHY", "CONFUSED_WORDS", "REPETITIONS",
    "REDUNDANCY", "REPETITIONS_STYLE", "STYLE", "PLAIN_ENGLISH", "GENDER_NEUTRALITY", "SEMANTICS",
    "COLLOQUIALISMS", "REGIONALISMS", "FALSE_FRIENDS", "WIKIPEDIA", "MISC",
}


def test_every_named_category_is_a_real_languagetool_category():
    from proofline.settings_widgets import CATEGORY_NAMES

    assert set(CATEGORY_NAMES) <= LANGUAGETOOL_CATEGORIES


@pytest.mark.parametrize(("language", "expected"), [("auto", "lang=en"), ("de-DE", "lang=de-DE"), ("en-US", "lang=en-US")])
def test_rules_link_follows_the_language(language, expected):
    from proofline.settings_widgets import rule_browser_url

    assert rule_browser_url(language) == f"https://community.languagetool.org/rule/list?{expected}"


def test_checking_page_links_to_rule_and_category_documentation(qtbot, tmp_path):
    from proofline.settings_window import SettingsWindow

    window = SettingsWindow(lambda: Config(language="en-US"), lambda c: c, tmp_path / "logs")
    qtbot.addWidget(window)
    window.show_settings()
    assert "rule/list?lang=en-US" in window.checking.rules_link.text()
    assert "Categories.java" in window.checking.categories_link.text()
