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
