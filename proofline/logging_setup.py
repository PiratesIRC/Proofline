"""Console + rotating file logging.

PROOFLINE_LOG_LEVEL sets console verbosity. Typed text is only logged in debug
mode, switched on from Settings or with PROOFLINE_LOG_TEXT=1. The names from before the
rename (LT_DESKTOP_LOG_LEVEL, LT_DESKTOP_LOG_TEXT) still work.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from proofline.config import APP_DATA_DIR

LOG_DIR = APP_DATA_DIR / "logs"
# Used when LOG_DIR cannot be written, such as a portable copy in a read-only folder.
FALLBACK_LOG_DIR = Path(tempfile.gettempdir()) / "Proofline" / "logs"
LOG_FILE_NAME = "app.log"
LOG_LEVEL_ENV = "PROOFLINE_LOG_LEVEL"
LOG_TEXT_ENV = "PROOFLINE_LOG_TEXT"
ENV_PREFIX = "PROOFLINE_"
OLD_ENV_PREFIX = "LT_DESKTOP_"  # before the rename
DEFAULT_CONSOLE_LEVEL = logging.INFO
MAX_LOG_BYTES = 2_000_000
LOG_BACKUPS = 3
NOISY_LOGGERS = ("urllib3", "comtypes", "anthropic", "httpx", "httpx2", "httpcore", "httpcore2")
LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"

_debug_mode = threading.Event()


def set_debug_mode(enabled: bool) -> None:
    """Called whenever the config changes; read from any thread."""
    if enabled == _debug_mode.is_set():
        return
    if enabled:
        _debug_mode.set()
    else:
        _debug_mode.clear()
    logging.getLogger(__name__).info("Debug mode %s", "on" if enabled else "off")


def env_setting(name: str, default: str = "") -> str:
    """An environment variable, falling back to its name from before the rename."""
    value = os.environ.get(name)
    if value is None:
        value = os.environ.get(name.replace(ENV_PREFIX, OLD_ENV_PREFIX, 1), default)
    return value


def text_logging_enabled() -> bool:
    """Typed text is only written to logs when the user opts in for diagnostics."""
    return _debug_mode.is_set() or env_setting(LOG_TEXT_ENV).strip() == "1"


def setup_logging(log_dir: Path = LOG_DIR, fallback_dir: Path = FALLBACK_LOG_DIR) -> tuple[logging.Handler, ...]:
    """Attach file and console handlers to the root logger and return them.

    When log_dir cannot be written, the log goes to fallback_dir and its first line says why.
    """
    formatter = logging.Formatter(LOG_FORMAT)
    try:
        file_handler = _file_handler(log_dir)
        unwritable = None
    except OSError as exc:
        file_handler = _file_handler(fallback_dir)
        unwritable = exc
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    requested = env_setting(LOG_LEVEL_ENV, "INFO").strip().upper()
    console_level = logging.getLevelNamesMapping().get(requested)
    handlers: tuple[logging.Handler, ...] = (file_handler,)
    # The packaged (windowed) exe has no console, so sys.stderr is None there.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(DEFAULT_CONSOLE_LEVEL if console_level is None else console_level)
        console_handler.setFormatter(formatter)
        handlers = (file_handler, console_handler)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in handlers:
        root.addHandler(handler)
    # These log every connection / COM object release at DEBUG; keep them quiet. anthropic also
    # logs each request body at DEBUG, which holds the text sent to the AI.
    for noisy in NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if unwritable is not None:
        logging.getLogger(__name__).warning("Could not write the log in %s (%s); logging here instead",
                                            log_dir, unwritable)
    if console_level is None:
        logging.getLogger(__name__).warning(
            "Ignoring invalid %s=%r; using INFO", LOG_LEVEL_ENV, requested
        )
    return handlers


def _file_handler(log_dir: Path) -> RotatingFileHandler:
    log_dir.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(log_dir / LOG_FILE_NAME, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS,
                               encoding="utf-8")


def current_log_path() -> Path | None:
    """The file the root logger writes to, or None before setup_logging (or if it failed)."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RotatingFileHandler):
            return Path(handler.baseFilename)
    return None
