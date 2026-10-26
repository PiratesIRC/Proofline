import json
from datetime import datetime

import pytest

from proofline.ai_prices import cost, price_for
from proofline.ai_usage import UsageEntry, can_spend, read_entries, record, totals

NOW = datetime(2026, 10, 26, 12, 0)


def entry(when=NOW, cost_=0.01, estimated=False):
    return UsageEntry(when, "rephrase", "claude-haiku-5-5", 1000, 200, cost_, estimated)


def test_cost_uses_the_model_price():
    assert cost("claude-haiku-5-5", 1_000_000, 1_000_000) == 0.60
    assert cost("claude-opus-5-5", 1000, 500) == 0.014


def test_unknown_model_has_no_price():
    assert price_for("gpt-x") is None
    with pytest.raises(KeyError):
        cost("gpt-x", 1, 1)


def test_ledger_round_trip(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    first, second = entry(), entry(datetime(2026, 10, 25, 9, 30), 0.5, True)
    record(first, path)
    record(second, path)
    assert read_entries(path) == [first, second]


def test_ledger_never_stores_text(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    record(entry(), path)
    keys = set(json.loads(path.read_text(encoding="utf-8")))
    assert keys == {"when", "job", "model", "input_tokens", "output_tokens", "cost", "estimated"}


def test_missing_ledger_reads_as_empty(tmp_path):
    assert read_entries(tmp_path / "none.jsonl") == []


def test_corrupt_line_is_skipped(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    record(entry(), path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{bad\n")
    record(entry(), path)
    assert len(read_entries(path)) == 2


def test_month_total_ignores_last_month():
    entries = [entry(datetime(2026, 9, 30, 23, 59), 0.30), entry(datetime(2026, 10, 1, 0, 0), 0.20)]
    result = totals(entries, NOW)
    assert result.month == 0.20
    assert result.requests_month == 1
    assert result.today == 0


def test_today_counts_only_today():
    result = totals([entry(NOW, 0.05), entry(datetime(2026, 10, 25, 23, 0), 0.07)], NOW)
    assert result.today == 0.05
    assert result.month == pytest.approx(0.12)


def test_can_spend_refuses_at_and_over_the_cap():
    assert can_spend(0.99, 1.0, 0.01)
    assert not can_spend(1.0, 1.0, 0.000001)
    assert not can_spend(0.5, 1.0, 0.6)


def test_entry_after_a_half_written_line_is_kept(tmp_path):
    # A crash mid-write leaves a fragment with no newline; the next entry must not join it.
    path = tmp_path / "ai_usage.jsonl"
    record(entry(), path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"when": "2026-10')
    record(entry(), path)
    assert len(read_entries(path)) == 2
