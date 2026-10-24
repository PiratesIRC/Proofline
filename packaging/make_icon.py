"""Write the exe icon (the tray's P badge) as a multi-size .ico for PyInstaller.

Usage: python packaging/make_icon.py <output.ico>
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofline.tray import ACTIVE_COLOR, make_icon

ICON_PX = 256

log = logging.getLogger(__name__)


def main(output: Path) -> int:
    _app = QGuiApplication(sys.argv[:1])
    output.parent.mkdir(parents=True, exist_ok=True)
    # Qt's ICO writer stores the image; Windows scales it for smaller sizes.
    if not make_icon(ACTIVE_COLOR).pixmap(ICON_PX, ICON_PX).save(str(output), "ICO"):
        log.error("Could not write %s", output)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        log.error("Usage: python packaging/make_icon.py <output.ico>")
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
