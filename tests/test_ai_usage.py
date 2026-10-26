import json
from datetime import datetime

import pytest

from proofline.ai_prices import cost, price_for
from proofline.ai_usage import (
    TokenTotals,
    UsageEntry,
    can_spend,
    read_entries,
    record,
    token_totals,
    totals,
)

NOW = datetime(2026, 10, 26, 12, 0)


def entry(when=NOW, job="rephrase", model="claude-haiku-5-5", input_tokens=1000, output_tokens=200,
          cost=0.01, estimated=False, provider="anthropic", cost_known=True):
    return UsageEntry(when, job, model, input_tokens, output_tokens, cost, estimated, provider, cost_known)


def test_cost_uses_the_model_price():
    assert cost(price_for("anthropic", "claude-haiku-5-5"), 1_000_000, 1_000_000) == 0.60
    assert cost(price_for("anthropic", "claude-opus-5-5"), 1000, 500) == 0.014


def test_unknown_model_has_no_price():
    assert price_for("anthropic", "gpt-x") is None


def test_ledger_round_trip(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    first = entry()
    second = entry(when=datetime(2026, 10, 25, 9, 30), cost=0.5, estimated=True)
    record(first, path)
    record(second, path)
    assert read_entries(path) == [first, second]


def test_ledger_never_stores_text(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    record(entry(provider="ollama", cost_known=False), path)
    keys = set(json.loads(path.read_text(encoding="utf-8")))
    assert keys == {"when", "job", "model", "input_tokens", "output_tokens", "cost", "estimated",
                    "provider", "cost_known"}


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
    entries = [entry(when=datetime(2026, 9, 30, 23, 59), cost=0.30),
               entry(when=datetime(2026, 10, 1, 0, 0), cost=0.20)]
    result = totals(entries, NOW)
    assert result.month == 0.20
    assert result.requests_month == 1
    assert result.today == 0


def test_today_counts_only_today():
    result = totals([entry(cost=0.05), entry(when=datetime(2026, 10, 25, 23, 0), cost=0.07)], NOW)
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


def test_old_lines_count_as_known_claude_cost(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    path.write_text('{"when": "2026-10-20T10:00:00", "job": "rephrase", "model": "claude-haiku-5-5", '
                    '"input_tokens": 100, "output_tokens": 50, "cost": 0.25, "estimated": false}\n',
                    encoding="utf-8")
    [old] = read_entries(path)
    assert (old.provider, old.cost_known) == ("anthropic", True)
    assert totals([old], NOW).month == 0.25


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    path.write_text('{"when": "2026-10-20T10:00:00", "job": "x", "model": "m", "input_tokens": 1, '
                    '"output_tokens": 1, "cost": 0.1, "estimated": false, "future": 7}\n', encoding="utf-8")
    assert len(read_entries(path)) == 1


def test_non_object_line_is_skipped(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    path.write_text('5\n["list"]\n', encoding="utf-8")
    assert read_entries(path) == []


def test_unknown_cost_left_out_of_dollars_but_counted_in_tokens():
    entries = [entry(provider="ollama", cost=0.0, cost_known=False, input_tokens=1000, output_tokens=240),
               entry(provider="openai", cost=0.5)]
    assert totals(entries, NOW).month == 0.5
    assert totals(entries, NOW).requests_month == 2
    assert token_totals(entries, NOW, "ollama") == TokenTotals(1240, 1240, 1)


def test_token_totals_count_only_the_given_provider_this_month():
    entries = [entry(input_tokens=10, output_tokens=5),
               entry(when=datetime(2026, 10, 25, 9, 0), provider="anthropic", input_tokens=100, output_tokens=20),
               entry(provider="anthropic", input_tokens=7, output_tokens=3),
               entry(when=datetime(2026, 9, 30, 9, 0), input_tokens=999, output_tokens=999)]
    assert token_totals(entries, NOW, "anthropic") == TokenTotals(
        today=10 + 5 + 7 + 3, month=10 + 5 + 100 + 20 + 7 + 3, requests_month=3)


def test_new_fields_round_trip(tmp_path):
    record(entry(provider="gemini", cost_known=False), tmp_path / "u.jsonl")
    [back] = read_entries(tmp_path / "u.jsonl")
    assert (back.provider, back.cost_known) == ("gemini", False)


def test_claude_line_has_no_provider_or_cost_known_keys(tmp_path):
    """A Claude line stays identical to what 0.3.x wrote, so it has no provider or cost_known key."""
    path = tmp_path / "ai_usage.jsonl"
    record(UsageEntry(NOW, "rephrase", "claude-haiku-5-5", 10, 2, 0.001, False), path)
    [raw] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert "provider" not in raw and "cost_known" not in raw
    assert set(raw) == {"when", "job", "model", "input_tokens", "output_tokens", "cost", "estimated"}


def test_other_provider_line_keeps_provider_and_cost_known(tmp_path):
    path = tmp_path / "ai_usage.jsonl"
    record(UsageEntry(NOW, "rephrase", "gemini-2.5-pro", 10, 2, 0.001, False, provider="gemini"), path)
    record(UsageEntry(NOW, "rephrase", "llama3", 10, 2, 0.0, False, provider="ollama", cost_known=False), path)
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert (raw[0]["provider"], "cost_known" in raw[0]) == ("gemini", False)
    assert (raw[1]["provider"], raw[1]["cost_known"]) == ("ollama", False)
    assert read_entries(path)[1].cost_known is False
