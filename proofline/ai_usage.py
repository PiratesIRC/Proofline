"""The AI usage ledger and the monthly spending cap.

One JSON line per AI request in ai_usage.jsonl, beside config.json: when, which job,
which model and provider, the token counts, the cost, and whether that cost is known (Ollama
and Other have no price, so their dollars are left out of totals). The text sent is never stored.
A request that was sent but returned no token counts is recorded at its worst-case cost
(estimated=True), so the recorded total is never below what was spent. Lines written before the
provider fields existed read as Claude with a known cost, so they keep counting.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

from proofline.ai_providers import DEFAULT_PROVIDER
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
    provider: str = DEFAULT_PROVIDER
    cost_known: bool = True  # False for an unpriced provider; its cost is left out of dollar totals


@dataclass(frozen=True)
class Totals:
    today: float
    month: float
    requests_month: int


@dataclass(frozen=True)
class TokenTotals:
    today: int
    month: int
    requests_month: int


def _line_fields(entry: UsageEntry) -> dict:
    """The entry as stored. provider and cost_known are written only when they differ from their defaults,
    so Claude lines stay identical to what 0.3.x wrote."""
    raw = {**asdict(entry), "when": entry.when.isoformat(timespec="seconds")}
    if entry.provider == DEFAULT_PROVIDER:
        del raw["provider"]
    if entry.cost_known:
        del raw["cost_known"]
    return raw


def record(entry: UsageEntry, path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_line_fields(entry))
    with path.open("a+b") as handle:
        # A crash mid-write leaves a fragment with no newline; start this entry on its own line.
        if handle.tell() > 0:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                line = "\n" + line
        handle.write((line + "\n").encode("utf-8"))


def _from_raw(raw: dict) -> UsageEntry:
    """Build an entry from a stored line, ignoring keys this version does not know."""
    known = {f.name for f in fields(UsageEntry)}
    kwargs = {k: v for k, v in raw.items() if k in known}
    return UsageEntry(**{**kwargs, "when": datetime.fromisoformat(raw["when"])})


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
            entries.append(_from_raw(json.loads(line)))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            log.warning("Skipping unreadable line %d in %s (%s)", number, path.name, exc)
    return entries


def _this_month(entries: list[UsageEntry], now: datetime) -> list[UsageEntry]:
    return [e for e in entries if (e.when.year, e.when.month) == (now.year, now.month)]


def totals(entries: list[UsageEntry], now: datetime) -> Totals:
    """Dollar sums skip entries whose cost is unknown; the request count includes them."""
    month = _this_month(entries, now)
    priced = [e for e in month if e.cost_known]
    priced_today = [e for e in priced if e.when.date() == now.date()]
    return Totals(
        today=round(sum(e.cost for e in priced_today), 6),
        month=round(sum(e.cost for e in priced), 6),
        requests_month=len(month),
    )


def token_totals(entries: list[UsageEntry], now: datetime, provider: str) -> TokenTotals:
    """Input plus output tokens, and the request count, for one provider."""
    month = [e for e in _this_month(entries, now) if e.provider == provider]
    today = [e for e in month if e.when.date() == now.date()]
    return TokenTotals(
        today=sum(e.input_tokens + e.output_tokens for e in today),
        month=sum(e.input_tokens + e.output_tokens for e in month),
        requests_month=len(month),
    )


def can_spend(month_total: float, cap: float, worst_case: float) -> bool:
    """True when a request costing up to worst_case keeps this month within cap."""
    return month_total + worst_case <= cap
