"""Is a newer Proofline release on GitHub? Checked in the background, at most daily.

The latest version is the `tag_name` of the repository's latest GitHub release. The
result is cached in a JSON file and re-checked when the installed version changed,
24 hours after a success, or 2 hours after a failure. Windows only ever read the
cache (cached_info); UpdateChecker refreshes it on a worker thread, so opening
Settings never waits on the network. Nothing here raises: every failure becomes the
"Version check unavailable" status. Sends no typed text, only an anonymous request.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from proofline import __version__
from proofline.config import APP_DATA_DIR
from proofline.workers import run_in_background

log = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/PiratesIRC/Proofline/releases/latest"
RELEASES_PAGE_URL = "https://github.com/PiratesIRC/Proofline/releases"
USER_AGENT = "Proofline-Version-Checker"
REQUEST_TIMEOUT_S = 10
SUCCESS_TTL_S = 24 * 60 * 60
FAILURE_TTL_S = 2 * 60 * 60
TICK_MS = 60 * 60 * 1000  # how often the app asks whether the cache has gone stale
CACHE_PATH = APP_DATA_DIR / "version_check.json"
NON_DIGITS = re.compile(r"\D")

CURRENT, OUTDATED, UNKNOWN = "current", "outdated", "unknown"

Getter = Callable[..., Any]


@dataclass(frozen=True)
class VersionInfo:
    status: str  # CURRENT, OUTDATED or UNKNOWN
    message: str  # one line for the UI
    latest: str = ""


def unavailable(current: str) -> VersionInfo:
    return VersionInfo(UNKNOWN, f"Version check unavailable (v{_bare(current)})")


def fetch_latest_version(get: Getter = requests.get) -> str | None:
    """The latest release's tag, or None on any HTTP, network or format problem."""
    try:
        response = get(LATEST_RELEASE_URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S)
        if response.status_code != 200:
            log.info("Update check: GitHub answered HTTP %d", response.status_code)
            return None
        tag = response.json().get("tag_name")
    except (requests.RequestException, ValueError, AttributeError) as exc:
        log.info("Update check failed: %s", exc)
        return None
    return tag if isinstance(tag, str) and tag.strip() else None


def compare_versions(current: str, latest: str) -> VersionInfo:
    """Outdated only when latest is numerically greater; a newer local build is current."""
    current, latest = _bare(current), _bare(latest)
    if current == latest:
        return VersionInfo(CURRENT, f"You are up to date (v{current})", latest)
    try:
        newer = _parts(latest) > _parts(current)
    except ValueError:
        return VersionInfo(UNKNOWN, f"Version check unavailable (current: v{current}, latest: {latest})", latest)
    if newer:
        return VersionInfo(OUTDATED, f"Update available: {latest} (current: v{current})", latest)
    return VersionInfo(CURRENT, f"You are up to date (v{current})", latest)


def cached_info(current: str, path: Path = CACHE_PATH) -> VersionInfo | None:
    """The cached result for this installed version, without any network call."""
    cache = _load(path)
    if not cache or cache.get("app_version") != current:
        return None
    info = cache.get("version_info") or {}
    return VersionInfo(str(info.get("status", UNKNOWN)), str(info.get("message", "")), str(info.get("latest", "")))


def check_for_update(
    current: str, path: Path = CACHE_PATH, now: float | None = None, fetch: Callable[[], str | None] = fetch_latest_version,
    force: bool = False,
) -> VersionInfo:
    """The cached result while it is fresh, otherwise (or when forced) a new check, saved to the cache."""
    now = time.time() if now is None else now
    cache = _load(path)
    if cache and not force and not _is_stale(cache, current, now):
        return cached_info(current, path) or unavailable(current)
    latest = fetch()
    info = compare_versions(current, latest) if latest else unavailable(current)
    _save(path, {
        "timestamp": now,
        "app_version": current,
        "latest_version": latest,
        "version_info": {"status": info.status, "message": info.message, "latest": info.latest},
    })
    return info


def _is_stale(cache: dict, current: str, now: float) -> bool:
    if cache.get("app_version") != current:
        return True
    ok = (cache.get("version_info") or {}).get("status") in (CURRENT, OUTDATED)
    age = now - float(cache.get("timestamp") or 0)
    return age >= (SUCCESS_TTL_S if ok else FAILURE_TTL_S)


def _bare(version: str) -> str:
    version = version.strip()
    return version[1:] if version[:1] in ("v", "V") else version


def _parts(version: str) -> list[int]:
    parts = [NON_DIGITS.sub("", part) for part in version.split(".")]
    if not all(parts):
        raise ValueError(f"not a numeric version: {version!r}")
    return [int(part) for part in parts]


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(path: Path, data: dict) -> None:
    """Write via a temporary file in the same folder and os.replace, so a reader never sees half a file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        os.replace(temp, path)
    except OSError as exc:
        log.warning("Could not save the update check result: %s", exc)


class UpdateChecker(QObject):
    """Refreshes the cache on a worker thread at start and then hourly while it is stale.

    checked(VersionInfo) follows each refresh. newer_version(str) fires once per new
    release version, so the app can notify without repeating itself.
    """

    checked = pyqtSignal(object)  # VersionInfo
    newer_version = pyqtSignal(str)

    def __init__(
        self, enabled: Callable[[], bool], current: str = __version__, path: Path = CACHE_PATH,
        check: Callable[..., VersionInfo] = check_for_update, tick_ms: int = TICK_MS,
    ) -> None:
        super().__init__()
        self._enabled = enabled
        self._current = current
        self._path = path
        self._check = check
        self._running = False
        self._announced = ""
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.check_now)

    def start(self) -> None:
        self._timer.start()
        self.check_now()

    def stop(self) -> None:
        self._timer.stop()

    def current_info(self) -> VersionInfo | None:
        """What windows show: the cached result only, never a network call."""
        return cached_info(self._current, self._path)

    def check_now(self, force: bool = False) -> None:
        """Refresh if stale; force (the Check now button) asks GitHub now, even with checks off."""
        if self._running or not (force or self._enabled()):
            return
        self._running = True
        current, path, check = self._current, self._path, self._check
        task = (lambda: check(current, path, force=True)) if force else (lambda: check(current, path))
        run_in_background(task, self._on_done, self._on_failed)

    def _on_done(self, info: VersionInfo) -> None:
        self._running = False
        self.checked.emit(info)
        if info.status == OUTDATED and info.latest != self._announced:
            self._announced = info.latest
            self.newer_version.emit(info.latest)

    def _on_failed(self, exc: Exception) -> None:
        self._running = False
        log.warning("Update check failed unexpectedly: %s", exc)
