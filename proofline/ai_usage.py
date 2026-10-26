"""The AI usage ledger and the monthly spending cap.

One JSON line per Claude API request in ai_usage.jsonl, beside config.json: when, which job,
which model, the token counts and the cost. The text sent is never stored. A request that was
sent but returned no token counts is recorded at its worst-case cost (estimated=True), so the
recorded total is never below what was spent.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from proofline.config import APP_DATA_DIR

log = logging.getLogger(__name__)

LEDGER_PATH = APP_DATA_DIR / "ai_usage.jsonl"


@dataclass(frozen=True)
class UsageEntry:
    when: datetime  # local time
    job: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float  # dollars
    estimated: bool  # True when no token counts came back and the worst case was recorded


@dataclass(frozen=True)
class Totals:
    today: float
    month: float
    requests_month: int


def record(entry: UsageEntry, path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({**asdict(entry), "when": entry.when.isoformat(timespec="seconds")})
    with path.open("a+b") as handle:
        # A crash mid-write leaves a fragment with no newline; start this entry on its own line.
        if handle.tell() > 0:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                line = "\n" + line
        handle.write((line + "\n").encode("utf-8"))


def read_entries(path: Path = LEDGER_PATH) -> list[UsageEntry]:
    """Every readable entry; a damaged line (say, from a crash mid-write) is skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    entries = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            entries.append(UsageEntry(**{**raw, "when": datetime.fromisoformat(raw["when"])}))
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("Skipping unreadable line %d in %s (%s)", number, path.name, exc)
    return entries


def totals(entries: list[UsageEntry], now: datetime) -> Totals:
    month = [e for e in entries if (e.when.year, e.when.month) == (now.year, now.month)]
    today = [e for e in month if e.when.date() == now.date()]
    return Totals(
        today=round(sum(e.cost for e in today), 6),
        month=round(sum(e.cost for e in month), 6),
        requests_month=len(month),
    )


def can_spend(month_total: float, cap: float, worst_case: float) -> bool:
    """True when a request costing up to worst_case keeps this month within cap."""
    return month_total + worst_case <= cap
