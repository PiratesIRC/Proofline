import winreg

import pytest

from proofline.legacy import (
    LEGACY_APP_ID,
    LEGACY_RUN_VALUE,
    migrate_app_data,
    remove_legacy_registry,
)
from proofline.logging_setup import env_setting

TEST_ROOT = r"Software\ProoflineTest"
TEST_RUN = rf"{TEST_ROOT}\Run"
TEST_AUMID = rf"{TEST_ROOT}\AppUserModelId"


def test_old_folder_moves_to_new(tmp_path):
    old, new = tmp_path / "LanguageToolDesktop", tmp_path / "Proofline"
    (old / "logs").mkdir(parents=True)
    (old / "config.json").write_text("{}", encoding="utf-8")
    message = migrate_app_data(old, new)
    assert "Moved" in message
    assert (new / "config.json").is_file() and (new / "logs").is_dir()
    assert not old.exists()


@pytest.mark.parametrize("old_exists, new_exists", [(False, False), (True, True), (False, True)])
def test_nothing_happens_without_an_old_only_folder(tmp_path, old_exists, new_exists):
    old, new = tmp_path / "old", tmp_path / "new"
    if old_exists:
        old.mkdir()
        (old / "config.json").write_text('{"old": 1}', encoding="utf-8")
    if new_exists:
        new.mkdir()
    assert migrate_app_data(old, new) == ""
    assert old.exists() == old_exists


def test_config_is_copied_when_the_folder_cannot_be_renamed(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    (old / "config.json").write_text('{"picky": true}', encoding="utf-8")

    def locked(self, target):
        raise PermissionError("in use")

    monkeypatch.setattr(type(old), "rename", locked)
    message = migrate_app_data(old, new)
    assert "Copied" in message
    assert (new / "config.json").read_text(encoding="utf-8") == '{"picky": true}'
    assert old.exists()


@pytest.fixture
def test_keys():
    yield
    for path in (rf"{TEST_AUMID}\{LEGACY_APP_ID}", TEST_AUMID, TEST_RUN, TEST_ROOT):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


def _value_exists(key_path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return False
    return True


def test_old_registry_entries_are_removed(test_keys):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, TEST_RUN) as key:
        winreg.SetValueEx(key, LEGACY_RUN_VALUE, 0, winreg.REG_SZ, "old.exe")
        winreg.SetValueEx(key, "Other", 0, winreg.REG_SZ, "keep.exe")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{TEST_AUMID}\{LEGACY_APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "LanguageTool Desktop")

    remove_legacy_registry(TEST_RUN, TEST_AUMID)

    assert not _value_exists(TEST_RUN, LEGACY_RUN_VALUE)
    assert _value_exists(TEST_RUN, "Other")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_AUMID}\{LEGACY_APP_ID}")


def test_registry_cleanup_without_old_entries_is_quiet(test_keys):
    remove_legacy_registry(TEST_RUN, TEST_AUMID)  # keys absent: no error


def test_env_setting_prefers_new_name_and_accepts_old(monkeypatch):
    monkeypatch.delenv("PROOFLINE_LOG_LEVEL", raising=False)
    monkeypatch.setenv("LT_DESKTOP_LOG_LEVEL", "DEBUG")
    assert env_setting("PROOFLINE_LOG_LEVEL", "INFO") == "DEBUG"
    monkeypatch.setenv("PROOFLINE_LOG_LEVEL", "WARNING")
    assert env_setting("PROOFLINE_LOG_LEVEL", "INFO") == "WARNING"
    monkeypatch.delenv("LT_DESKTOP_LOG_LEVEL")
    monkeypatch.delenv("PROOFLINE_LOG_LEVEL")
    assert env_setting("PROOFLINE_LOG_LEVEL", "INFO") == "INFO"
