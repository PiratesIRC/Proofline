"""Give the process its own Windows identity so notifications and the taskbar show
"Proofline" and our icon instead of "Python".

Windows attributes tray notifications to the process's AppUserModelID; for apps
without a Start-menu shortcut, the name and icon come from
HKCU\\Software\\Classes\\AppUserModelId\\<id>.
"""

from __future__ import annotations

import ctypes
import logging
import winreg
from pathlib import Path

from PyQt6.QtGui import QIcon

from proofline.config import APP_DATA_DIR

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = "PiratesIRC.Proofline"
DISPLAY_NAME = "Proofline"
ICON_PATH = APP_DATA_DIR / "app-icon.png"
ICON_PX = 256
AUMID_KEY_PARENT = r"Software\Classes\AppUserModelId"


def set_process_app_id(app_id: str = APP_USER_MODEL_ID) -> None:
    """Must run before any window or tray icon is created."""
    result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    if result != 0:
        log.warning("Could not set AppUserModelID (HRESULT %#x)", result & 0xFFFFFFFF)


def register_app_id(
    icon: QIcon,
    app_id: str = APP_USER_MODEL_ID,
    icon_path: Path = ICON_PATH,
    key_parent: str = AUMID_KEY_PARENT,
) -> None:
    """Write the icon file and the per-user registry entry naming this app."""
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    if not icon.pixmap(ICON_PX, ICON_PX).save(str(icon_path), "PNG"):
        raise OSError(f"Could not write {icon_path}")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, rf"{key_parent}\{app_id}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon_path))
    log.info("Registered app identity %s", app_id)
