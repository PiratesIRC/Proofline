"""Run blocking calls on Qt's thread pool and deliver results on the GUI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from proofline.ai_types import AiError

log = logging.getLogger(__name__)

# Keeps tasks alive until their result has been delivered.
_active_tasks: set[_Task] = set()


def _describe(exc: Exception) -> str:
    """The exception's type, and an AiError's kind. Never its text: a provider's own words can carry a URL or a key."""
    kind = exc.kind if isinstance(exc, AiError) else None
    return type(exc).__name__ if kind is None else f"{type(exc).__name__}, {kind}"


class _Signals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - any failure is reported via on_error
            log.debug("Background task failed (%s)", _describe(exc))
            self.signals.failed.emit(exc)
            return
        self.signals.succeeded.emit(result)


def run_in_background(
    fn: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
) -> None:
    task = _Task(fn)
    _active_tasks.add(task)

    def finish(callback: Callable[[Any], None], value: Any) -> None:
        _active_tasks.discard(task)
        callback(value)

    task.signals.succeeded.connect(lambda result: finish(on_success, result))
    task.signals.failed.connect(lambda exc: finish(on_error, exc))
    QThreadPool.globalInstance().start(task)
