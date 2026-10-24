"""Start with Windows: add or remove this app from the per-user Run registry key.

Uses HKEY_CURRENT_USER only, so no administrator rights are needed.
"""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Proofline"

PYTHONW_NAME = "pythonw.exe"
MAIN_SCRIPT_NAME = "main.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AutostartError(Exception):
    """Raised when the Start with Windows setting cannot be read or changed."""


def launch_command(python_exe: Path | None = None, script: Path | None = None) -> str:
    """Return the command line Windows should run at sign-in.

    A packaged build runs its own exe. Otherwise uses pythonw.exe (no console window)
    next to the running interpreter when it exists, else the interpreter itself.
    """
    if python_exe is None and script is None and is_frozen():
        return f'"{sys.executable}"'
    python = python_exe or _default_python()
    main_script = script or PROJECT_ROOT / MAIN_SCRIPT_NAME
    return f'"{python}" "{main_script}"'


def is_frozen() -> bool:
    """True when running from the PyInstaller build rather than from source."""
    return bool(getattr(sys, "frozen", False))


def _default_python() -> Path:
    current = Path(sys.executable)
    pythonw = current.with_name(PYTHONW_NAME)
    return pythonw if pythonw.exists() else current


def is_enabled(key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    """True if the Run value exists. Unreadable keys are reported as disabled."""
    return stored_command(key_path, value_name) is not None


def stored_command(key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> str | None:
    """The command in the Run value, or None if it is absent or unreadable."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE
        ) as key:
            value, _type = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("Could not read Start with Windows setting: %s", exc)
        return None
    return str(value)


def set_enabled(
    enabled: bool,
    command: str | None = None,
    key_path: str = RUN_KEY,
    value_name: str = VALUE_NAME,
) -> None:
    """Add (enabled=True) or remove (enabled=False) the Run value.

    Removing a value that is already absent is not an error.
    Raises AutostartError if the registry cannot be written.
    """
    try:
        if enabled:
            _write_value(key_path, value_name, command or launch_command())
        else:
            _delete_value(key_path, value_name)
    except OSError as exc:
        raise AutostartError(
            "Could not change the 'Start with Windows' setting. "
            "Check that your Windows account can write to the registry."
        ) from exc
    log.info("Start with Windows %s", "enabled" if enabled else "disabled")


def _write_value(key_path: str, value_name: str, command: str) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, command)


def _delete_value(key_path: str, value_name: str) -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        return
