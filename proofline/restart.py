"""Restart Proofline: start a second copy that waits for this one to quit.

Only one copy runs at a time (a lock file, see main.py). The new copy is started with
RESTART_ARG, which makes it wait for the lock instead of reporting "already running";
the old copy then quits and releases the lock.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess

from proofline.autostart import MAIN_SCRIPT_NAME, PROJECT_ROOT, PYTHONW_NAME, is_frozen

log = logging.getLogger(__name__)

RESTART_ARG = "--restarted"
RESTART_LOCK_TIMEOUT_MS = 15_000  # how long the new copy waits for the old one to quit

Starter = Callable[[str, list[str]], object]


def restart_command() -> tuple[str, list[str]]:
    """The program and arguments that start this app again: the packaged exe, or pythonw + main.py."""
    if is_frozen():
        return sys.executable, [RESTART_ARG]
    current = Path(sys.executable)
    pythonw = current.with_name(PYTHONW_NAME)
    python = pythonw if pythonw.exists() else current
    return str(python), [str(PROJECT_ROOT / MAIN_SCRIPT_NAME), RESTART_ARG]


def start_new_copy(start: Starter = QProcess.startDetached) -> bool:
    """Start the new copy; False when Windows could not start it (the caller then keeps running)."""
    program, arguments = restart_command()
    started = start(program, arguments)
    ok = bool(started[0]) if isinstance(started, tuple) else bool(started)
    if not ok:
        log.warning("Could not start a new copy for the restart")
    return ok


def is_restart(argv: list[str]) -> bool:
    return RESTART_ARG in argv
