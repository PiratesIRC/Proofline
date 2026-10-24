import pytest
from PyQt6.QtCore import Qt

from proofline.config import Config
from proofline.list_editor import StringListEditor


@pytest.fixture
def editor(qtbot):
    widget = StringListEditor("Apps:", "e.g. KeePass.exe")
    qtbot.addWidget(widget)
    return widget


def test_add_strips_and_rejects_blank_and_duplicates(editor):
    assert editor.add_item("  KeePass.exe ")
    assert not editor.add_item("keepass.EXE")
    assert not editor.add_item("   ")
    assert editor.items() == ("KeePass.exe",)


def test_enter_in_input_adds_and_clears(qtbot, editor):
    qtbot.keyClicks(editor._input, "mstsc.exe")
    qtbot.keyClick(editor._input, Qt.Key.Key_Return)
    assert editor.items() == ("mstsc.exe",)
    assert editor._input.text() == ""


def test_remove_selected(editor):
    editor.set_items(("a.exe", "b.exe", "c.exe"))
    assert not editor._remove_button.isEnabled()
    editor._list.item(1).setSelected(True)
    assert editor._remove_button.isEnabled()
    editor._remove_button.click()
    assert editor.items() == ("a.exe", "c.exe")


def test_new_config_has_recommended_exclusions():
    config = Config()
    assert config.is_disabled_for("KeePass.exe", "Database - KeePass")
    assert config.is_disabled_for("vivaldi.exe", "Rhombus - Console Login - Vivaldi")
    assert not config.is_disabled_for("OUTLOOK.EXE", "Inbox - Outlook")

