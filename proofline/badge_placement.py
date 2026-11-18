"""Where a dragged badge goes back to, remembered per text box.

A saved spot is a corner of the box plus an offset in logical pixels, so it follows the box when
the window moves or resizes and when Windows scaling changes. Boxes are identified by a hash of
what UI Automation reports about them; no title or typed text is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect

from proofline.badge import BADGE_SIZE
from proofline.config import (
    FIELD_SIGNATURE_SEPARATOR,
    field_signature,
    saveable_signature,
)
from proofline.text_snapshot import FieldSnapshot

MAX_SAVED_SPOTS = 200
KEY_CHARS = 32
CORNERS = ("tl", "tr", "bl", "br")
TIE_ORDER = ("br", "tr", "bl", "tl")  # the automatic position is bottom-right
ENTRY_SEPARATOR = "="
SPOT_SEPARATOR = ":"

# Electron apps (Teams, Slack, Discord) are left out on purpose: their titles change per channel.
BROWSERS = frozenset({
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "arc.exe", "zen.exe", "librewolf.exe", "waterfox.exe", "floorp.exe", "thorium.exe",
})
BROWSER_NAMES = (
    "Google Chrome", "Chromium", "Microsoft Edge", "Mozilla Firefox Private Browsing", "Mozilla Firefox",
    "Brave", "Opera GX", "Opera", "Vivaldi", "Arc", "Zen Browser", "LibreWolf", "Waterfox", "Floorp", "Thorium",
)
_SUFFIX = re.compile(r"\s(?:-|\u2014)\s(?:" + "|".join(re.escape(n) for n in BROWSER_NAMES) + r")$")
_MORE_PAGES = re.compile(r" and \d+ more pages?")
_LEADING_COUNTER = re.compile(r"^\(\d+\+?\) ")
_SEGMENT_COUNTER = re.compile(r" \(\d+\+?\)(?= - |$)")
_KEY = re.compile(r"[0-9a-f]{32}")
_OFFSET = re.compile(r"-?[0-9]+")  # int() alone also takes "+5", "5_0" and non-ASCII digits


@dataclass(frozen=True)
class SavedSpot:
    corner: str
    dx: int
    dy: int


def page_title(window_title: str) -> str:
    """A browser window title without the browser's name, tab count and unread counters."""
    title = _SUFFIX.sub("", window_title)
    title = _MORE_PAGES.sub("", title)
    title = _LEADING_COUNTER.sub("", title)
    return _SEGMENT_COUNTER.sub("", title)


def field_key(snapshot: FieldSnapshot, secret: str) -> str:
    """A 32-character keyed hash naming this text box across sessions.

    secret (badge_secret.load_secret) is kept out of config.json, so a shared config or
    diagnostics report cannot be used to confirm a guessed page title.
    """
    signature = saveable_signature(field_signature(snapshot.process_name, snapshot.control_type, snapshot.class_name))
    title = page_title(snapshot.window_title) if snapshot.process_name.casefold() in BROWSERS else ""
    key = FIELD_SIGNATURE_SEPARATOR.join((signature, snapshot.automation_id, title)).casefold()
    return hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()[:KEY_CHARS]


def corner_point(field: QRect, corner: str) -> QPoint:
    return {"tl": field.topLeft(), "tr": field.topRight(), "bl": field.bottomLeft(), "br": field.bottomRight()}[corner]


def spot_for(badge_top_left: QPoint, field: QRect) -> SavedSpot:
    """The corner nearest the badge centre and the badge's offset from it."""
    centre = badge_top_left + QPoint(BADGE_SIZE // 2, BADGE_SIZE // 2)

    def distance(corner: str) -> int:
        d = centre - corner_point(field, corner)
        return d.x() * d.x() + d.y() * d.y()

    corner = min(TIE_ORDER, key=distance)  # min keeps the first of equal values
    offset = badge_top_left - corner_point(field, corner)
    return SavedSpot(corner, offset.x(), offset.y())


def clamp(point: QPoint, available: QRect) -> QPoint:
    """point moved so the whole badge lies inside available (QRect right/bottom are inclusive)."""
    x = max(available.left(), min(point.x(), available.right() - BADGE_SIZE + 1))
    y = max(available.top(), min(point.y(), available.bottom() - BADGE_SIZE + 1))
    return QPoint(x, y)


def area_for(badge_top_left: QPoint, areas: Sequence[QRect], home: QRect) -> QRect:
    """The available area holding the badge centre, else the nearest one; home when there are none."""
    centre = badge_top_left + QPoint(BADGE_SIZE // 2, BADGE_SIZE // 2)

    def distance(area: QRect) -> int:
        dx = max(area.left() - centre.x(), 0, centre.x() - area.right())
        dy = max(area.top() - centre.y(), 0, centre.y() - area.bottom())
        return dx * dx + dy * dy

    return min(areas, key=distance, default=home)


def place(spot: SavedSpot, field: QRect, areas: Sequence[QRect], home: QRect) -> QPoint:
    """The saved spot for field, kept on whichever screen it lands on (a badge may sit on
    another monitor than its field); clamped to home when it lands on none."""
    point = corner_point(field, spot.corner) + QPoint(spot.dx, spot.dy)
    return clamp(point, area_for(point, areas, home))


def encode(key: str, spot: SavedSpot) -> str:
    return f"{key}{ENTRY_SEPARATOR}{spot.corner}{SPOT_SEPARATOR}{spot.dx}{SPOT_SEPARATOR}{spot.dy}"


def decode(entry: str) -> tuple[str, SavedSpot] | None:
    key, separator, value = entry.partition(ENTRY_SEPARATOR)
    parts = value.split(SPOT_SEPARATOR)
    if not separator or not _KEY.fullmatch(key) or len(parts) != 3 or parts[0] not in CORNERS:
        return None
    if not (_OFFSET.fullmatch(parts[1]) and _OFFSET.fullmatch(parts[2])):
        return None
    return key, SavedSpot(parts[0], int(parts[1]), int(parts[2]))


def lookup(entries: tuple[str, ...], key: str) -> SavedSpot | None:
    for entry in reversed(entries):
        decoded = decode(entry)
        if decoded is not None and decoded[0] == key:
            return decoded[1]
    return None


def tidy(entries: tuple[str, ...]) -> tuple[str, ...]:
    """Valid entries only, the last one per box, the newest MAX_SAVED_SPOTS, oldest first."""
    latest: dict[str, str] = {}
    for entry in entries:
        decoded = decode(entry)
        if decoded is not None:
            latest.pop(decoded[0], None)  # re-inserting moves the box to the end
            latest[decoded[0]] = encode(*decoded)
    return tuple(latest.values())[-MAX_SAVED_SPOTS:]


def without_spot(entries: tuple[str, ...], key: str) -> tuple[str, ...]:
    return tuple(e for e in entries if (decoded := decode(e)) is None or decoded[0] != key)


def with_spot(entries: tuple[str, ...], key: str, spot: SavedSpot) -> tuple[str, ...]:
    return tidy((*without_spot(entries, key), encode(key, spot)))
