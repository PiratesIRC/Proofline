"""Apply the app's light, dark, or automatic (follow Windows) colour scheme."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

THEMES = ("auto", "light", "dark")
_SCHEME_BY_THEME = {
    "auto": Qt.ColorScheme.Unknown,
    "light": Qt.ColorScheme.Light,
    "dark": Qt.ColorScheme.Dark,
}


def apply_theme(app: QGuiApplication, theme: str) -> None:
    """Set the colour scheme. 'auto' hands control back to the operating system."""
    scheme = _SCHEME_BY_THEME.get(theme)
    if scheme is None:
        raise ValueError(f"Unknown theme {theme!r}; expected one of {THEMES}")
    app.styleHints().setColorScheme(scheme)
    log.info("Applied %s theme", theme)


def is_dark(app: QGuiApplication) -> bool:
    """True when the application is currently using a dark colour scheme."""
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
