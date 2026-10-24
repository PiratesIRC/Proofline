"""One-time move from the app's old name (LanguageTool Desktop) to Proofline.

Settings and logs move from %LOCALAPPDATA%\\LanguageToolDesktop to the new folder, and the
old per-user registry entries (Start with Windows value, notification identity key) are
removed. Every step is skipped when there is nothing to do, so this runs on each start.
The new Start with Windows value is written from the config by DesktopIntegration.
"""

from __future__ import annotations

import logging
import shutil
import winreg
from pathlib import Path

from proofline.app_identity import AUMID_KEY_PARENT
from proofline.autostart import RUN_KEY
from proofline.config import APP_DATA_DIR

log = logging.getLogger(__name__)

LEGACY_DATA_DIR = APP_DATA_DIR.parent / "LanguageToolDesktop"
LEGACY_APP_ID = "PiratesIRC.LanguageToolDesktop"
LEGACY_RUN_VALUE = "LanguageToolDesktop"
CONFIG_FILE_NAME = "config.json"


def migrate_app_data(old: Path = LEGACY_DATA_DIR, new: Path = APP_DATA_DIR) -> str:
    """Move old to new when only old exists. Returns what happened for the log ('' = nothing).

    Runs before logging starts, so it reports instead of logging. If the folder can't be
    renamed (a file still open), only config.json is copied and the old folder is left.
    """
    if not old.is_dir() or new.exists():
        return ""
    try:
        old.rename(new)
        return f"Moved settings and logs from {old} to {new}"
    except OSError as exc:
        rename_error = exc
    try:
        new.mkdir(parents=True)
        if (old / CONFIG_FILE_NAME).is_file():
            shutil.copy2(old / CONFIG_FILE_NAME, new / CONFIG_FILE_NAME)
    except OSError as exc:
        return f"Could not move settings from {old} to {new}: {exc}"
    return f"Copied settings from {old} to {new} ({rename_error}); the old folder can be deleted"


def remove_legacy_registry(run_key: str = RUN_KEY, aumid_parent: str = AUMID_KEY_PARENT) -> None:
    """Delete the old Start with Windows value and the old notification identity key."""
    if _delete(run_key, LEGACY_RUN_VALUE):
        log.info("Removed the old Start with Windows entry %s", LEGACY_RUN_VALUE)
    if _delete(rf"{aumid_parent}\{LEGACY_APP_ID}"):
        log.info("Removed the old notification identity %s", LEGACY_APP_ID)


def _delete(key_path: str, value_name: str | None = None) -> bool:
    """Delete a value (value_name given) or a whole key under HKCU; True if it existed."""
    try:
        if value_name is None:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.warning("Could not remove %s %s: %s", key_path, value_name or "", exc)
        return False
    return True
