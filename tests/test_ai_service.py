import threading
from datetime import datetime

import pytest

from proofline.ai_client import AiError, AiRequest, AiResult
from proofline.ai_prices import cost
from proofline.ai_service import (
    BUSY_MESSAGE,
    CAP_MESSAGE,
    NO_KEY_MESSAGE,
    OFF_MESSAGE,
    TOO_LONG_MESSAGE,
    AiService,
)
from proofline.ai_usage import UsageEntry, read_entries, record
from proofline.config import Config

NOW = datetime(2026, 10, 26, 12, 0)
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def request(text="This are a test.", max_tokens=2000):
    return AiRequest("rephrase", "Reword it.", text, SCHEMA, max_tokens)


class FakeBackend:
    def __init__(self, result=None, error=None, gate=None):
        self.result = result or AiResult({"ok": True}, 1200, 300)
        self.error, self.gate, self.calls = error, gate, []

    def send(self, req, model):
        self.calls.append((req, model))
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        return self.result


class Harness:
    def __init__(self, qtbot, tmp_path, backend, config=None, key="sk-ant-test"):
        self.ledger = tmp_path / "ai_usage.jsonl"
        self.config = config or Config(ai_enabled=True)
        self.backend = backend
        self.keys = []
        self.service = AiService(lambda: self.config, self._factory, lambda: key, self.ledger, lambda: NOW)
        self.failures = []
        self.kinds = []
        self.service.failed.connect(lambda req, message, kind: (self.failures.append(message),
                                                                self.kinds.append(kind)))
        self.qtbot = qtbot

    def _factory(self, key):
        self.keys.append(key)
        return self.backend


def test_refused_when_ai_is_off(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(), config=Config())
    assert h.service.submit(request()) is False
    assert h.failures == [OFF_MESSAGE] == ["AI is turned off in Settings."]
    assert h.backend.calls == []


def test_refused_without_a_key(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(), key=None)
    assert h.service.submit(request()) is False
    assert h.failures == [NO_KEY_MESSAGE] == ["Add an API key in Settings, AI."]


def test_refused_over_8000_characters(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend())
    assert h.service.submit(request("x" * 8001)) is False
    assert h.failures == [TOO_LONG_MESSAGE] == ["Select a shorter part (at most 8,000 characters)."]


def test_exactly_8000_characters_is_sent(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend())
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request("x" * 8000)) is True


def test_refused_when_the_worst_case_crosses_the_cap(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(), config=Config(ai_enabled=True, ai_model="claude-opus-5-5"))
    record(UsageEntry(NOW, "rephrase", "claude-opus-5-5", 0, 0, 0.999, False), h.ledger)
    assert h.service.submit(request(max_tokens=4000)) is False
    assert h.failures == [CAP_MESSAGE] == ["Monthly AI limit reached."]
    assert h.backend.calls == []


def test_last_month_spending_does_not_count(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend())
    record(UsageEntry(datetime(2026, 9, 30, 22, 0), "rephrase", "claude-haiku-5-5", 0, 0, 5.0, False), h.ledger)
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True


def test_one_request_at_a_time(qtbot, tmp_path):
    gate = threading.Event()
    h = Harness(qtbot, tmp_path, FakeBackend(gate=gate))
    assert h.service.submit(request()) is True
    assert h.service.busy
    assert h.service.submit(request()) is False
    assert h.failures == [BUSY_MESSAGE] == ["Another AI request is still running."]
    with qtbot.waitSignal(h.service.finished):
        gate.set()
    assert not h.service.busy
    assert len(h.backend.calls) == 1


def test_success_records_actual_usage_and_sends_the_model_and_key(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend())
    with qtbot.waitSignal(h.service.finished) as blocker:
        h.service.submit(request())
    assert blocker.args[1] == AiResult({"ok": True}, 1200, 300)
    assert h.backend.calls[0][1] == "claude-haiku-5-5"
    assert h.keys == ["sk-ant-test"]
    [entry] = read_entries(h.ledger)
    assert (entry.input_tokens, entry.output_tokens, entry.estimated) == (1200, 300, False)
    assert entry.cost == cost("claude-haiku-5-5", 1200, 300)
    assert entry.job == "rephrase"


@pytest.mark.parametrize("kind", ["timeout", "network", "server"])
def test_unknown_outcome_records_the_worst_case(qtbot, tmp_path, kind):
    h = Harness(qtbot, tmp_path, FakeBackend(error=AiError(kind, "The request failed.")))
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request(max_tokens=2000))
    [entry] = read_entries(h.ledger)
    assert entry.estimated is True
    assert entry.output_tokens == 2000
    assert not h.service.busy


@pytest.mark.parametrize("kind", ["auth", "rate_limit"])
def test_rejected_request_records_nothing(qtbot, tmp_path, kind):
    h = Harness(qtbot, tmp_path, FakeBackend(error=AiError(kind, "Rejected.")))
    with qtbot.waitSignal(h.service.failed) as blocker:
        h.service.submit(request())
    assert blocker.args[1] == "Rejected."
    assert read_entries(h.ledger) == []


def test_refusal_with_token_counts_records_them(qtbot, tmp_path):
    error = AiError("refusal", "Claude declined this request.", input_tokens=900, output_tokens=10)
    h = Harness(qtbot, tmp_path, FakeBackend(error=error))
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request())
    [entry] = read_entries(h.ledger)
    assert (entry.input_tokens, entry.output_tokens, entry.estimated) == (900, 10, False)


def test_unexpected_exception_is_reported_and_recorded_at_worst_case(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(error=RuntimeError("boom")))
    with qtbot.waitSignal(h.service.failed) as blocker:
        h.service.submit(request())
    assert blocker.args[1] == "The AI request failed."
    assert read_entries(h.ledger)[0].estimated is True


def test_month_totals_read_the_ledger(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend())
    record(UsageEntry(NOW, "rephrase", "claude-haiku-5-5", 0, 0, 0.25, False), h.ledger)
    assert h.service.month_totals().month == 0.25


def test_failed_carries_the_kind(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(), config=Config())
    h.service.submit(request())
    assert h.kinds == ["off"]
    h = Harness(qtbot, tmp_path, FakeBackend(error=AiError("timeout", "slow")))
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request())
    assert h.kinds == ["timeout"]
    h = Harness(qtbot, tmp_path, FakeBackend(error=RuntimeError("boom")))
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request())
    assert h.kinds == ["error"]


def _service(config, loader):
    return AiService(lambda: config, lambda key: FakeBackend(), loader)


def test_available_needs_switch_and_key():
    assert not _service(Config(), lambda: "sk-ant-x").available()
    assert not _service(Config(ai_enabled=True), lambda: None).available()
    assert _service(Config(ai_enabled=True), lambda: "sk-ant-x").available()

    def broken():
        raise OSError("credential store unavailable")

    assert not _service(Config(ai_enabled=True), broken).available()


def test_available_reads_the_key_store_once_until_key_changed():
    loads = []

    def loader():
        loads.append(1)
        return "sk-ant-x"

    service = _service(Config(ai_enabled=True), loader)
    service.available()
    service.available()
    assert len(loads) == 1
    service.key_changed()
    service.available()
    assert len(loads) == 2


def test_rejected_key_hides_ai_until_the_key_changes_or_a_request_succeeds(qtbot, tmp_path):
    backend = FakeBackend(error=AiError("auth", "The Claude API did not accept the API key."))
    h = Harness(qtbot, tmp_path, backend)
    assert h.service.available()
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request())
    assert not h.service.available()
    h.service.key_changed()
    assert h.service.available()
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request())
    assert not h.service.available()
    backend.error = None  # the Settings Test button still sends, and success restores AI
    with qtbot.waitSignal(h.service.finished):
        h.service.submit(request())
    assert h.service.available()
