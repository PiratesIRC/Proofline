"""main.main(): a failure during startup is shown in a message box, not only logged."""

import main as entry


def test_a_startup_failure_shows_the_error_and_the_log_path(qapp, monkeypatch, tmp_path):
    shown = []
    log_path = tmp_path / "app.log"

    def broken_start():
        raise RuntimeError("settings folder is read-only")

    monkeypatch.setattr(entry, "_run", broken_start)
    monkeypatch.setattr(entry, "current_log_path", lambda: log_path)
    monkeypatch.setattr(entry.QMessageBox, "critical", lambda parent, title, text: shown.append(text))
    assert entry.main() == 1
    assert len(shown) == 1
    assert "settings folder is read-only" in shown[0]
    assert str(log_path) in shown[0]
