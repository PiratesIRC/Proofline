import pytest

from proofline.config import Config
from proofline.diagnostics import build_report, clear_logs
from proofline.logging_setup import LOG_FILE_NAME, set_debug_mode, text_logging_enabled


@pytest.fixture(autouse=True)
def debug_off(monkeypatch):
    monkeypatch.delenv("PROOFLINE_LOG_TEXT", raising=False)
    set_debug_mode(False)
    yield
    set_debug_mode(False)


@pytest.fixture
def log_dir(tmp_path):
    lines = [f"line {i}" for i in range(300)]
    (tmp_path / LOG_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / f"{LOG_FILE_NAME}.1").write_text("old", encoding="utf-8")
    return tmp_path


def test_debug_mode_flag_and_env_var(monkeypatch):
    assert not text_logging_enabled()
    set_debug_mode(True)
    assert text_logging_enabled()
    set_debug_mode(False)
    monkeypatch.setenv("PROOFLINE_LOG_TEXT", "1")
    assert text_logging_enabled()


def test_report_has_environment_redacted_settings_and_log_tail(log_dir):
    config = Config(server_url="https://user:secret@lt.example/v2/check")
    report = build_report(config, log_dir, max_lines=5)
    assert "Windows:" in report and "Python:" in report
    assert "secret" not in report
    assert "Debug:     off" in report
    assert report.splitlines()[-5:] == [f"line {i}" for i in range(295, 300)]


def test_report_flags_debug_mode(log_dir):
    set_debug_mode(True)
    assert "may contain typed text" in build_report(Config(), log_dir)


def test_report_without_log_file(tmp_path):
    assert "(no log file yet)" in build_report(Config(), tmp_path)


def test_clear_logs_truncates_current_and_deletes_backups(log_dir):
    assert clear_logs(log_dir) == 2
    assert (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8") == ""
    assert not (log_dir / f"{LOG_FILE_NAME}.1").exists()

