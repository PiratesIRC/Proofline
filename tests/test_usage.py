import json
from dataclasses import replace

import pytest

from proofline.config import Config
from proofline.usage import (
    AI_COUNTER,
    AI_LABEL,
    AI_PLUGIN,
    COUNTER,
    LABEL,
    PLUGIN,
    UsageReporting,
    ledger_total,
    make_ai_reporter,
    make_reporter,
    record_ai_rephrase,
    record_correction,
    usage_settings,
)


def test_reporter_matches_the_worker_allowlist_entry(tmp_path):
    reporter = make_reporter(dict, ledger=tmp_path / "l.jsonl", data_dir=tmp_path / "usage")
    # plugin-stats worker/src/config.js: "proofline": { counter: "corrections_applied", ... }
    assert (reporter.plugin, reporter.counter, reporter.label) == ("proofline", "corrections_applied", "Corrections Applied")
    assert (PLUGIN, COUNTER, LABEL) == ("proofline", "corrections_applied", "Corrections Applied")


def test_ledger_total_sums_lines_and_missing_file_is_zero(tmp_path):
    ledger = tmp_path / "usage_counts.jsonl"
    assert ledger_total(ledger) == 0
    assert record_correction(ledger) and record_correction(ledger)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write(json.dumps({"corrections_applied": 3}) + "\n")
    assert ledger_total(ledger) == 5


def test_ledger_lines_hold_only_a_count_and_a_time(tmp_path):
    ledger = tmp_path / "usage_counts.jsonl"
    record_correction(ledger)
    line = json.loads(ledger.read_text(encoding="utf-8"))
    assert set(line) == {"corrections_applied", "ts"} and line["corrections_applied"] == 1


def test_failed_ledger_write_returns_false(tmp_path):
    assert record_correction(tmp_path / "missing-dir" / "sub" / "x.jsonl") is True  # folders are created
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    assert record_correction(blocker / "x.jsonl") is False  # parent is a file


@pytest.mark.parametrize("share", [True, False])
def test_settings_follow_the_live_config(share):
    assert usage_settings(Config(share_usage_counts=share)) == {"share_usage_counts": share}


class FakeReporter:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def report(self, settings=None, logger=None, force=False):
        self.calls.append((settings, force))
        if self.error:
            raise self.error


def reporting(config, reporter, record=lambda: True, ai_reporter=None, record_ai=lambda: True):
    holder = {"config": config}
    usage = UsageReporting(lambda: holder["config"], reporter=reporter, record=record,
                           ai_reporter=ai_reporter or FakeReporter(), record_ai=record_ai)
    return usage, holder


def test_start_reports_once_with_the_live_settings():
    reporter = FakeReporter()
    usage, _ = reporting(Config(), reporter)
    usage.start()
    usage.stop()
    assert reporter.calls == [({"share_usage_counts": True}, False)]


def test_a_raising_reporter_never_breaks_the_app():
    usage, _ = reporting(Config(), FakeReporter(error=RuntimeError("boom")))
    usage.report()  # no exception
    usage.on_correction_applied()


def test_successful_ledger_write_reports_with_force():
    reporter = FakeReporter()
    usage, _ = reporting(Config(), reporter, record=lambda: True)
    usage.on_correction_applied()
    assert reporter.calls == [({"share_usage_counts": True}, True)]


def test_failed_ledger_write_does_not_report():
    reporter = FakeReporter()
    usage, _ = reporting(Config(), reporter, record=lambda: False)
    usage.on_correction_applied()
    assert reporter.calls == []


def test_opting_out_reports_the_new_setting_at_once():
    reporter = FakeReporter()
    usage, holder = reporting(Config(), reporter)
    holder["config"] = replace(Config(), share_usage_counts=False)
    usage.on_setting_changed()
    assert reporter.calls == [({"share_usage_counts": False}, False)]


def test_real_client_sends_the_ledger_total_on_windows_and_deletes_on_opt_out(tmp_path):
    """End to end through the vendored client with its send stubbed: no network."""
    ledger, sent = tmp_path / "usage_counts.jsonl", []
    record_correction(ledger)
    record_correction(ledger)
    share = {"on": True}

    def http(method, url, body):
        sent.append((method, url, body))
        return 202 if method == "POST" else 204

    reporter = make_reporter(lambda: {"share_usage_counts": share["on"]}, ledger=ledger,
                             data_dir=tmp_path / "usage", http=http, start=lambda fn: fn())
    reporter.report({"share_usage_counts": True})
    method, url, body = sent[-1]
    assert (method, body["plugin"], body["counter"], body["total"]) == ("POST", "proofline", "corrections_applied", 2)
    assert url == "https://plugin-stats.dpas.workers.dev/v1/report"
    assert len(body["install"]) == 32 and (tmp_path / "usage" / "proofline" / "sent").exists()

    reporter.report({"share_usage_counts": True})
    assert len(sent) == 1  # at most once an hour

    share["on"] = False
    reporter.report({"share_usage_counts": False})
    assert sent[-1][0] == "DELETE" and not (tmp_path / "usage" / "proofline" / "install_id").exists()


def test_ai_reporter_matches_its_worker_allowlist_entry(tmp_path):
    reporter = make_ai_reporter(dict, ledger=tmp_path / "a.jsonl", data_dir=tmp_path / "usage")
    # plugin-stats worker/src/config.js: "proofline-ai": { counter: "ai_rephrases", ... }
    assert (reporter.plugin, reporter.counter, reporter.label) == ("proofline-ai", "ai_rephrases", "AI Rephrases")
    assert (AI_PLUGIN, AI_COUNTER, AI_LABEL) == ("proofline-ai", "ai_rephrases", "AI Rephrases")


def test_ai_ledger_lines_hold_only_a_count_and_a_time(tmp_path):
    ledger = tmp_path / "ai.jsonl"
    assert record_ai_rephrase(ledger)
    line = json.loads(ledger.read_text(encoding="utf-8"))
    assert set(line) == {"ai_rephrases", "ts"} and line["ai_rephrases"] == 1


def test_applied_ai_rephrase_reports_only_the_ai_count():
    reporter, ai_reporter = FakeReporter(), FakeReporter()
    usage, _ = reporting(Config(), reporter, ai_reporter=ai_reporter)
    usage.on_ai_rephrase_applied()
    assert ai_reporter.calls == [({"share_usage_counts": True}, True)] and reporter.calls == []


def test_start_and_opt_out_reach_both_counts():
    reporter, ai_reporter = FakeReporter(), FakeReporter()
    usage, holder = reporting(Config(), reporter, ai_reporter=ai_reporter)
    usage.start()
    usage.stop()
    holder["config"] = replace(Config(), share_usage_counts=False)
    usage.on_setting_changed()
    assert ai_reporter.calls == reporter.calls == [({"share_usage_counts": True}, False),
                                                   ({"share_usage_counts": False}, False)]
