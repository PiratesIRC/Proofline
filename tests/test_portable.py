from pathlib import Path

from proofline.config import PORTABLE_DATA_DIR_NAME, PORTABLE_MARKER, app_data_dir


def test_source_run_uses_localappdata(tmp_path):
    assert app_data_dir(frozen=False, executable=tmp_path / "python.exe", local_app_data=str(tmp_path / "LA")) == (
        tmp_path / "LA" / "Proofline", False)


def test_installed_build_without_marker_uses_localappdata(tmp_path):
    exe = tmp_path / "app" / "Proofline.exe"
    exe.parent.mkdir()
    assert app_data_dir(frozen=True, executable=exe, local_app_data=str(tmp_path / "LA")) == (
        tmp_path / "LA" / "Proofline", False)


def test_portable_build_keeps_data_beside_the_exe(tmp_path):
    exe = tmp_path / "Proofline" / "Proofline.exe"
    exe.parent.mkdir()
    (exe.parent / PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert app_data_dir(frozen=True, executable=exe, local_app_data=str(tmp_path / "LA")) == (
        exe.parent / PORTABLE_DATA_DIR_NAME, True)


def test_marker_is_ignored_when_running_from_source(tmp_path):
    (tmp_path / PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    data_dir, portable = app_data_dir(frozen=False, executable=tmp_path / "python.exe", local_app_data=str(tmp_path))
    assert not portable and data_dir == Path(tmp_path) / "Proofline"


def test_portable_copy_imports_settings_from_an_installed_copy_once(tmp_path):
    from proofline.config import import_settings_into_portable

    installed, portable = tmp_path / "LA" / "Proofline", tmp_path / "Proofline" / "data"
    installed.mkdir(parents=True)
    (installed / "config.json").write_text('{"picky": true}', encoding="utf-8")
    message = import_settings_into_portable(portable, installed)
    assert "Copied" in message
    assert (portable / "config.json").read_text(encoding="utf-8") == '{"picky": true}'
    assert (installed / "config.json").exists()  # copied, never moved
    (installed / "config.json").write_text('{"picky": false}', encoding="utf-8")
    assert import_settings_into_portable(portable, installed) == ""  # only when it has none of its own
    assert (portable / "config.json").read_text(encoding="utf-8") == '{"picky": true}'


def test_portable_copy_without_installed_settings_starts_fresh(tmp_path):
    from proofline.config import import_settings_into_portable

    assert import_settings_into_portable(tmp_path / "data", tmp_path / "LA" / "Proofline") == ""
    assert not (tmp_path / "data" / "config.json").exists()
