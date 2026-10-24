from PyQt6.QtWidgets import QWidget

from proofline import window_corners


def test_round_corners_reports_success_or_failure_without_raising(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)

    assert isinstance(window_corners.round_corners(widget), bool)


def test_round_corners_returns_false_when_dwm_rejects(qtbot, monkeypatch):
    class FakeDwm:
        @staticmethod
        def DwmSetWindowAttribute(*_args):
            return -2147024809  # E_INVALIDARG, as on Windows 10

    class FakeWindll:
        dwmapi = FakeDwm()

    monkeypatch.setattr(window_corners.ctypes, "windll", FakeWindll())
    widget = QWidget()
    qtbot.addWidget(widget)

    assert window_corners.round_corners(widget) is False
