import winreg
from pathlib import Path

import pytest

from proofline import autostart
from proofline.autostart import AutostartError, is_enabled, launch_command, set_enabled

TEST_ROOT = r"Software\ProoflineTest"
TEST_KEY = TEST_ROOT + r"\Run"
TEST_VALUE = "ProoflineTest"


def _delete_tree(path: str) -> None:
    """Delete a registry key and all of its subkeys under HKEY_CURRENT_USER."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return
    with key:
        subkeys = [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]
    for name in subkeys:
        _delete_tree(f"{path}\\{name}")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


@pytest.fixture
def run_key():
    _delete_tree(TEST_ROOT)
    yield TEST_KEY
    _delete_tree(TEST_ROOT)


def _stored_value(key_path: str) -> str:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
        value, value_type = winreg.QueryValueEx(key, TEST_VALUE)
    assert value_type == winreg.REG_SZ
    return value


def test_enable_then_disable_round_trip(run_key):
    assert not is_enabled(run_key, TEST_VALUE)

    set_enabled(
        True,
        command='"C:\\py\\pythonw.exe" "C:\\app\\main.py"',
        key_path=run_key,
        value_name=TEST_VALUE,
    )
    assert is_enabled(run_key, TEST_VALUE)
    assert _stored_value(run_key) == '"C:\\py\\pythonw.exe" "C:\\app\\main.py"'

    set_enabled(False, key_path=run_key, value_name=TEST_VALUE)
    assert not is_enabled(run_key, TEST_VALUE)


def test_disable_when_absent_does_not_raise(run_key):
    set_enabled(False, key_path=run_key, value_name=TEST_VALUE)
    set_enabled(False, key_path=run_key, value_name=TEST_VALUE)
    assert not is_enabled(run_key, TEST_VALUE)


def test_enable_without_command_uses_launch_command(run_key, monkeypatch):
    monkeypatch.setattr(autostart, "launch_command", lambda: '"X" "Y"')
    set_enabled(True, key_path=run_key, value_name=TEST_VALUE)
    assert _stored_value(run_key) == '"X" "Y"'


def test_write_failure_raises_autostart_error(run_key, monkeypatch):
    def fail(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(autostart.winreg, "CreateKeyEx", fail)
    with pytest.raises(AutostartError, match="Start with Windows"):
        set_enabled(True, command="x", key_path=run_key, value_name=TEST_VALUE)


def test_launch_command_quotes_both_paths(tmp_path):
    python = tmp_path / "my python" / "pythonw.exe"
    script = tmp_path / "app dir" / "main.py"
    assert launch_command(python, script) == f'"{python}" "{script}"'


def test_launch_command_defaults_to_pythonw_and_main(monkeypatch, tmp_path):
    fake_python = tmp_path / "python.exe"
    fake_python.touch()
    (tmp_path / "pythonw.exe").touch()
    monkeypatch.setattr(autostart.sys, "executable", str(fake_python))

    command = launch_command()

    assert (
        command
        == f'"{tmp_path / "pythonw.exe"}" "{autostart.PROJECT_ROOT / "main.py"}"'
    )


def test_launch_command_falls_back_to_interpreter(monkeypatch, tmp_path):
    fake_python = tmp_path / "python.exe"
    fake_python.touch()
    monkeypatch.setattr(autostart.sys, "executable", str(fake_python))

    assert launch_command(script=Path("C:/app/main.py")).startswith(f'"{fake_python}" ')


def test_stored_command_reads_value_or_none(run_key):
    assert autostart.stored_command(run_key, TEST_VALUE) is None
    set_enabled(True, command=r'"C:\app\Proofline.exe"', key_path=run_key, value_name=TEST_VALUE)
    assert autostart.stored_command(run_key, TEST_VALUE) == r'"C:\app\Proofline.exe"'


def test_frozen_build_launches_its_own_exe(monkeypatch, tmp_path):
    exe = tmp_path / "Language Tool" / "Proofline.exe"
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(exe))

    assert autostart.is_frozen()
    assert launch_command() == f'"{exe}"'
