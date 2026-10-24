"""Support for the Settings 'Diagnostics' section: issue reports and log housekeeping."""

from __future__ import annotations

import logging
import platform
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

from proofline.config import Config
from proofline.logging_setup import LOG_DIR, LOG_FILE_NAME, text_logging_enabled

log = logging.getLogger(__name__)

REPORT_LOG_LINES = 200


def build_report(config: Config, log_dir: Path = LOG_DIR, max_lines: int = REPORT_LOG_LINES) -> str:
    """Plain-text report for pasting into an issue. Server credentials are redacted."""
    debug_note = "on (log lines may contain typed text)" if text_logging_enabled() else "off"
    header = [
        "Proofline diagnostic report",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Windows:   {platform.platform()}",
        f"Python:    {sys.version.split()[0]}",
        f"Qt:        {QT_VERSION_STR} (PyQt {PYQT_VERSION_STR})",
        f"Settings:  {config!r}",
        f"Debug:     {debug_note}",
        "",
        f"--- last {max_lines} log lines ---",
    ]
    return "\n".join(header + _tail(log_dir / LOG_FILE_NAME, max_lines))


def _tail(path: Path, max_lines: int) -> list[str]:
    try:
        with path.open(encoding="utf-8", errors="replace") as file:
            return [line.rstrip("\n") for line in deque(file, maxlen=max_lines)]
    except FileNotFoundError:
        return ["(no log file yet)"]
    except OSError as exc:
        return [f"(could not read log: {exc})"]


def clear_logs(log_dir: Path = LOG_DIR) -> int:
    """Empty the current log and delete rotated backups. Returns how many files were cleared."""
    cleared = 0
    for path in sorted(log_dir.glob(f"{LOG_FILE_NAME}*")):
        if path.name == LOG_FILE_NAME:
            # The file handler keeps this open in append mode, so truncate instead of deleting.
            path.write_text("", encoding="utf-8")
        else:
            path.unlink()
        cleared += 1
    log.info("Cleared %d log file(s)", cleared)
    return cleared
