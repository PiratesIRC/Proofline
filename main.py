"""Entry point: python main.py"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from proofline.app import LanguageToolApp
from proofline.app_identity import DISPLAY_NAME, register_app_id, set_process_app_id
from proofline.config import APP_DATA_DIR, IS_PORTABLE
from proofline.legacy import migrate_app_data, remove_legacy_registry
from proofline.logging_setup import setup_logging
from proofline.tray import ACTIVE_COLOR, make_icon

APP_NAME = DISPLAY_NAME
LOCK_FILE = APP_DATA_DIR / "app.lock"
LOCK_TIMEOUT_MS = 100


def main() -> int:
    # Before logging opens a file in the new folder. A portable copy keeps its own data.
    migrated = "" if IS_PORTABLE else migrate_app_data()
    setup_logging()
    log = logging.getLogger("main")
    sys.excepthook = lambda *exc_info: log.critical("Unhandled exception", exc_info=exc_info)
    if migrated:
        log.info(migrated)
    remove_legacy_registry()

    set_process_app_id()  # before any window exists, so Windows never attributes us to Python
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationDisplayName(APP_NAME)
    app_icon = make_icon(ACTIVE_COLOR)
    qt_app.setWindowIcon(app_icon)
    try:
        register_app_id(app_icon)
    except OSError:
        log.warning("Could not register app identity; notifications may show 'Python'", exc_info=True)

    # Held for the life of the process; Qt clears locks left by crashed processes.
    instance_lock = QLockFile(str(LOCK_FILE))
    if not instance_lock.tryLock(LOCK_TIMEOUT_MS):
        log.info("Another instance is already running; exiting")
        QMessageBox.information(
            None, APP_NAME, f"{APP_NAME} is already running. Look for the P icon in the tray."
        )
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "No system tray is available.")
        return 1

    app = LanguageToolApp(qt_app)
    app.start()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
