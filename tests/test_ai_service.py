import threading
from dataclasses import replace
from datetime import datetime

import pytest

from proofline import ai_prices
from proofline.ai_client import AiError, AiRequest, AiResult
from proofline.ai_jobs import find_issues_request
from proofline.ai_prices import (
    ModelPrice,
    cost,
    estimate_input_tokens,
    most_expensive,
    price_for,
)
from proofline.ai_providers import PROVIDER_IDS, provider
from proofline.ai_service import (
    BUSY_MESSAGE,
    CAP_MESSAGE,
    LOG_UNREADABLE_MESSAGE,
    NO_KEY_MESSAGE,
    OFF_MESSAGE,
    TOO_LONG_MESSAGE,
    AiService,
)
from proofline.ai_usage import TokenTotals, UsageEntry, read_entries, record
from proofline.config import Config

NOW = datetime(2026, 10, 26, 12, 0)
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
OPENROUTER_CHEAP = ModelPrice("openrouter", "cheap/model", "Cheap", 0.1, 0.1)
OPENROUTER_DEAR = ModelPrice("openrouter", "dear/model", "Dear", 50.0, 50.0)


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
        self.specs = []
        self.service = AiService(lambda: self.config, self._factory, lambda pid: key, self.ledger, lambda: NOW)
        self.failures = []
        self.kinds = []
        self.service.failed.connect(lambda req, message, kind: (self.failures.append(message),
                                                                self.kinds.append(kind)))
        self.qtbot = qtbot

    def _factory(self, spec, key, address):
        self.keys.append(key)
        self.specs.append((spec.id, key, address))
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
    assert entry.cost == cost(price_for("anthropic", "claude-haiku-5-5"), 1200, 300)
    assert (entry.job, entry.provider, entry.cost_known) == ("rephrase", "anthropic", True)


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
    return AiService(lambda: config, lambda spec, key, address: FakeBackend(), loader)


def test_available_needs_switch_and_key():
    assert not _service(Config(), lambda pid: "sk-ant-x").available()
    assert not _service(Config(ai_enabled=True), lambda pid: None).available()
    assert _service(Config(ai_enabled=True), lambda pid: "sk-ant-x").available()

    def broken(pid):
        raise OSError("credential store unavailable")

    assert not _service(Config(ai_enabled=True), broken).available()


def test_available_reads_the_key_store_once_until_key_changed():
    loads = []

    def loader(pid):
        loads.append(pid)
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


def test_key_only_loaded_for_selected_provider(qtbot, tmp_path):
    loads, specs = [], []

    def loader(pid):
        loads.append(pid)
        return f"k-{pid}"

    def factory(spec, key, address):
        specs.append((spec.id, key, address))
        return FakeBackend()

    service = AiService(lambda: Config(ai_enabled=True, ai_provider="openai"), factory, loader,
                        tmp_path / "ai_usage.jsonl", lambda: NOW)
    with qtbot.waitSignal(service.finished):
        assert service.submit(request()) is True
    assert loads == ["openai"]
    assert specs == [("openai", "k-openai", "")]


@pytest.mark.parametrize("pid", PROVIDER_IDS)
def test_find_job_uses_selected_provider(qtbot, tmp_path, pid):
    specs = []

    def factory(spec, key, address):
        specs.append(spec.id)
        return FakeBackend()

    config = Config(ai_enabled=True, ai_provider=pid, ai_models=(f"{pid}=test-model",))
    service = AiService(lambda: config, factory, lambda p: "k", tmp_path / "ai_usage.jsonl", lambda: NOW)
    if pid == "openrouter":
        service.set_live_prices(pid, (OPENROUTER_CHEAP, OPENROUTER_DEAR))
    with qtbot.waitSignal(service.finished):
        assert service.submit(find_issues_request("a b")) is True
    assert specs == [pid]


def test_unpriced_paths_never_call_the_price_table(qtbot, tmp_path, monkeypatch):
    def price_table_used(*args):
        raise AssertionError("the price table was used for an unpriced provider")

    monkeypatch.setattr("proofline.ai_service.cost", price_table_used)
    monkeypatch.setattr(ai_prices, "cost", price_table_used)
    monkeypatch.setattr("proofline.ai_service.price_for", price_table_used)
    monkeypatch.setattr(ai_prices, "price_for", price_table_used)
    current = {"backend": FakeBackend()}
    ledger = tmp_path / "ai_usage.jsonl"
    service = AiService(lambda: Config(ai_enabled=True, ai_provider="ollama", ai_models=("ollama=llama3",)),
                        lambda spec, key, address: current["backend"], lambda pid: None, ledger, lambda: NOW)
    with qtbot.waitSignal(service.finished):
        assert service.submit(request()) is True
    current["backend"] = FakeBackend(error=AiError("bad_response", "Ollama sent an unreadable answer.",
                                                   input_tokens=5, output_tokens=1))
    with qtbot.waitSignal(service.failed):
        assert service.submit(request()) is True
    current["backend"] = FakeBackend(error=AiError("timeout", "Ollama did not answer in time."))
    with qtbot.waitSignal(service.failed):
        assert service.submit(request()) is True
    entries = read_entries(ledger)
    assert [e.provider for e in entries] == ["ollama"] * 3
    assert [e.cost for e in entries] == [0.0] * 3
    assert [e.cost_known for e in entries] == [False] * 3
    assert (entries[1].input_tokens, entries[1].output_tokens) == (5, 1)
    assert entries[2].estimated is True


def test_typed_cloud_model_is_charged_at_the_most_expensive_price(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openai", ai_models=("openai=gpt-7-new",),
                    ai_monthly_cap_cents=1)
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    assert h.service.submit(request()) is False
    assert h.kinds == ["cap"]
    assert h.backend.calls == []
    h.config = replace(config, ai_monthly_cap_cents=10000)
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert entry.model == "gpt-7-new"
    assert entry.cost == cost(most_expensive("openai"), 1200, 300)


def test_rejected_key_for_one_provider_does_not_hide_another(qtbot, tmp_path):
    keys = {"anthropic": "sk-ant-x", "gemini": "gemini-key"}
    current = {"config": Config(ai_enabled=True)}
    backend = FakeBackend(error=AiError("auth", "The Claude API did not accept the API key."))
    service = AiService(lambda: current["config"], lambda spec, key, address: backend, keys.get,
                        tmp_path / "ai_usage.jsonl", lambda: NOW)
    assert service.available()
    with qtbot.waitSignal(service.failed):
        service.submit(request())
    assert not service.available()
    current["config"] = Config(ai_enabled=True, ai_provider="gemini")
    assert service.available()
    current["config"] = Config(ai_enabled=True)
    assert not service.available()
    service.key_changed("anthropic")
    assert service.available()


def test_ollama_needs_no_key_and_has_no_limit(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(),
                config=Config(ai_enabled=True, ai_provider="ollama", ai_monthly_cap_cents=10,
                              ai_models=("ollama=llama3",)), key=None)
    record(UsageEntry(NOW, "rephrase", "claude-haiku-5-5", 0, 0, 0.10, False), h.ledger)
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.failures == []
    assert h.service.available()


def test_openrouter_without_live_prices_is_refused(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=x/y",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    assert h.service.submit(request()) is False
    assert h.kinds == ["no_prices"]
    assert h.failures == ["Press Refresh to load OpenRouter's prices first."]
    assert h.backend.calls == []


@pytest.mark.parametrize("pid", ["openrouter", "ollama"])
def test_no_model_chosen_is_refused_before_any_send(qtbot, tmp_path, pid):
    h = Harness(qtbot, tmp_path, FakeBackend(), config=Config(ai_enabled=True, ai_provider=pid))
    if pid == "openrouter":
        h.service.set_live_prices(pid, (OPENROUTER_CHEAP, OPENROUTER_DEAR))
    assert h.service.submit(request()) is False
    assert h.kinds == ["no_model"]
    assert h.failures == ["Choose a model in Settings, AI."]
    assert h.specs == [] and h.backend.calls == []


def test_priced_model_with_unknown_price_is_refused(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("proofline.ai_service.most_expensive", lambda pid: None)
    config = Config(ai_enabled=True, ai_provider="openai", ai_models=("openai=gpt-7-new",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    assert h.service.submit(request()) is False
    assert h.kinds == ["no_price"]
    assert h.failures == ["This model's price is unknown, so the spending limit cannot be checked."]
    assert h.specs == [] and h.backend.calls == []


def test_openrouter_typed_model_limit_uses_worst_live_price(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=new/model",),
                    ai_monthly_cap_cents=1)
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP, OPENROUTER_DEAR))
    spec = provider("openrouter")
    assert h.service.price(spec, "cheap/model") == OPENROUTER_CHEAP
    assert h.service.price(spec, "new/model") == OPENROUTER_DEAR
    assert h.service.submit(request()) is False
    assert h.kinds == ["cap"]


class SequenceBackend:
    """Answers each send with the next queued result, or raises the next queued exception."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def send(self, req, model):
        self.calls.append((req, model))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_openrouter_reported_cost_is_recorded(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=0.0002))
    h = Harness(qtbot, tmp_path, backend, config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert (entry.cost, entry.cost_known) == (0.0002, True)


def test_openrouter_without_reported_cost_uses_list_price(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert entry.cost == cost(OPENROUTER_CHEAP, 1200, 300)


def test_deepseek_retries_once_and_records_both(qtbot, tmp_path):
    backend = SequenceBackend(AiError("bad_response", "unreadable", input_tokens=900, output_tokens=40),
                              AiResult({"ok": True}, 1200, 300))
    h = Harness(qtbot, tmp_path, backend, config=Config(ai_enabled=True, ai_provider="deepseek"))
    sent = []
    h.service.finished.connect(lambda req, result: sent.append(result))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert len(backend.calls) == 2
    assert sent == [AiResult({"ok": True}, 1200, 300)]
    assert h.failures == []
    assert not h.service.busy
    entries = read_entries(h.ledger)
    assert [(e.input_tokens, e.output_tokens, e.provider) for e in entries] == [
        (900, 40, "deepseek"), (1200, 300, "deepseek")]


def test_deepseek_retry_not_sent_when_it_would_exceed_the_limit(qtbot, tmp_path):
    backend = SequenceBackend(AiError("bad_response", "unreadable", input_tokens=900, output_tokens=100_000),
                              AiResult({"ok": True}, 1200, 300))
    config = Config(ai_enabled=True, ai_provider="deepseek", ai_monthly_cap_cents=10)
    h = Harness(qtbot, tmp_path, backend, config=config)
    with qtbot.waitSignal(h.service.failed):
        assert h.service.submit(request()) is True
    assert len(backend.calls) == 1
    assert h.kinds == ["bad_response"]
    assert h.failures == ["unreadable"]
    assert not h.service.busy
    [entry] = read_entries(h.ledger)
    assert entry.output_tokens == 100_000


def refuse_writes(entry, path):
    raise OSError("disk full")


def test_unwritable_ledger_still_counts_toward_the_limit(qtbot, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("proofline.ai_service.record", refuse_writes)
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=dear/model",),
                    ai_monthly_cap_cents=60)
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=0.50))
    h = Harness(qtbot, tmp_path, backend, config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_DEAR,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.service.month_totals().month == 0.5
    assert h.service.submit(request(max_tokens=8000)) is False
    assert h.kinds == ["cap"]
    assert len(backend.calls) == 1
    assert sum("Could not record AI usage" in r.getMessage() for r in caplog.records) == 1


def test_unwritable_ledger_entries_count_in_token_totals(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("proofline.ai_service.record", refuse_writes)
    h = Harness(qtbot, tmp_path, FakeBackend())
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.service.token_totals("anthropic") == TokenTotals(1500, 1500, 1)


def test_unreadable_ledger_refuses_priced_requests(qtbot, tmp_path, caplog):
    backend = FakeBackend()
    h = Harness(qtbot, tmp_path, backend)
    h.ledger.mkdir()  # a directory cannot be read as a log
    assert h.service.submit(request()) is False
    assert h.service.submit(request()) is False
    assert h.kinds == ["log_unreadable", "log_unreadable"]
    assert h.failures == [LOG_UNREADABLE_MESSAGE] * 2
    assert backend.calls == []
    assert sum("Could not read the AI usage log" in r.getMessage() for r in caplog.records) == 1


def test_unreadable_ledger_still_sends_ollama(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="ollama", ai_models=("ollama=llama3",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config, key=None)
    h.ledger.mkdir()
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.failures == []


def test_deepseek_retry_does_not_loop(qtbot, tmp_path):
    backend = SequenceBackend(AiError("bad_response", "unreadable", input_tokens=900, output_tokens=40),
                              AiError("bad_response", "still unreadable", input_tokens=900, output_tokens=40))
    h = Harness(qtbot, tmp_path, backend, config=Config(ai_enabled=True, ai_provider="deepseek"))
    with qtbot.waitSignal(h.service.failed):
        assert h.service.submit(request()) is True
    assert len(backend.calls) == 2
    assert h.failures == ["still unreadable"]
    assert h.kinds == ["bad_response"]
    assert not h.service.busy
    assert len(read_entries(h.ledger)) == 2


def test_retry_not_sent_once_ai_is_turned_off(qtbot, tmp_path):
    calls = []

    class SwitchOffThenFail:
        def send(self, req, model):
            calls.append(model)
            h.config = replace(h.config, ai_enabled=False)
            raise AiError("bad_response", "unreadable", input_tokens=900, output_tokens=40)

    h = Harness(qtbot, tmp_path, SwitchOffThenFail(), config=Config(ai_enabled=True, ai_provider="deepseek"))
    with qtbot.waitSignal(h.service.failed):
        assert h.service.submit(request()) is True
    assert len(calls) == 1
    assert h.failures == ["unreadable"]
    assert h.kinds == ["bad_response"]


def test_error_while_deciding_a_retry_still_reports_the_failure(qtbot, tmp_path, monkeypatch):
    real_read = read_entries
    reads = []

    def read_once(path):
        reads.append(path)
        if len(reads) > 1:  # the first read is submit's limit check; the second is the retry decision
            raise RuntimeError("ledger broke")
        return real_read(path)

    monkeypatch.setattr("proofline.ai_service.read_entries", read_once)
    backend = SequenceBackend(AiError("bad_response", "unreadable", input_tokens=900, output_tokens=40),
                              AiResult({"ok": True}, 1200, 300))
    h = Harness(qtbot, tmp_path, backend, config=Config(ai_enabled=True, ai_provider="deepseek"))
    with qtbot.waitSignal(h.service.failed):
        assert h.service.submit(request()) is True
    assert not h.service.busy
    assert h.failures == ["unreadable"]
    assert len(backend.calls) == 1


def test_bad_response_without_tokens_is_recorded_at_worst_case(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(error=AiError("bad_response", "unreadable")))
    with qtbot.waitSignal(h.service.failed):
        h.service.submit(request(max_tokens=2000))
    [entry] = read_entries(h.ledger)
    assert entry.estimated is True
    assert entry.output_tokens == 2000


@pytest.mark.parametrize("reported", [-50, float("nan")])
def test_other_server_reported_cost_is_ignored(qtbot, tmp_path, reported):
    config = Config(ai_enabled=True, ai_provider="other", ai_other_url="http://localhost:1234/v1",
                    ai_models=("other=local-model",))
    h = Harness(qtbot, tmp_path, FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=reported)),
                config=config)
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert (entry.cost, entry.cost_known) == (0.0, False)


@pytest.mark.parametrize("reported", [-1, float("nan"), float("inf")])
def test_openrouter_bad_reported_cost_falls_back_to_list_price(qtbot, tmp_path, reported):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=reported))
    h = Harness(qtbot, tmp_path, backend, config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert (entry.cost, entry.cost_known) == (cost(OPENROUTER_CHEAP, 1200, 300), True)


def test_openrouter_is_unavailable_until_its_prices_load(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter")
    service = AiService(lambda: config, lambda spec, key, address: FakeBackend(), lambda pid: "or-key",
                        tmp_path / "ai_usage.jsonl", lambda: NOW)
    assert not service.available()
    service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    assert service.available()


def test_other_key_is_never_sent_to_an_insecure_address(qtbot, tmp_path):
    """A hand-edited plain-http address on another computer gets no key, though one is saved."""
    config = Config(ai_enabled=True, ai_provider="other", ai_other_url="http://lan.example:1234/v1",
                    ai_models=("other=local-model",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config, key="sk-other")
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.keys == [None]


def other_config(address, key_address, models=("other=local-model",)):
    return Config(ai_enabled=True, ai_provider="other", ai_other_url=address, ai_other_key_address=key_address,
                  ai_models=models)


def test_other_key_is_sent_to_the_address_it_was_saved_for(qtbot, tmp_path):
    a = "http://localhost:1234/v1"
    h = Harness(qtbot, tmp_path, FakeBackend(), config=other_config(a, a), key="sk-other")
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.keys == ["sk-other"]


def test_other_key_is_not_sent_to_a_changed_address_even_after_a_restart(qtbot, tmp_path):
    """The key stays stored (its delete failed), but it is bound to the address it was saved for."""
    a, b = "http://localhost:1234/v1", "http://localhost:9999/v1"
    h = Harness(qtbot, tmp_path, FakeBackend(), config=other_config(b, a), key="sk-other")
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    restarted = Harness(qtbot, tmp_path, FakeBackend(), config=other_config(b, a), key="sk-other")
    with qtbot.waitSignal(restarted.service.finished):
        assert restarted.service.submit(request()) is True
    assert h.keys == [None] and restarted.keys == [None]


def test_other_key_is_sent_again_once_saved_for_the_new_address(qtbot, tmp_path):
    b = "http://localhost:9999/v1"
    h = Harness(qtbot, tmp_path, FakeBackend(), config=other_config(b, b), key="sk-new")
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.keys == ["sk-new"]


def test_other_key_never_bound_to_an_address_is_not_sent(qtbot, tmp_path):
    h = Harness(qtbot, tmp_path, FakeBackend(), config=other_config("http://localhost:1234/v1", ""),
                key="sk-other")
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    assert h.keys == [None]


def test_cost_uses_the_price_resolved_at_submit(qtbot, tmp_path):
    """The price list may change while a request is in flight; the request is charged at the price it was sent at."""
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    gate = threading.Event()
    h = Harness(qtbot, tmp_path, FakeBackend(gate=gate), config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    assert h.service.submit(request()) is True
    h.service.set_live_prices("openrouter", (OPENROUTER_DEAR,))
    with qtbot.waitSignal(h.service.finished):
        gate.set()
    [entry] = read_entries(h.ledger)
    assert entry.cost == cost(OPENROUTER_CHEAP, 1200, 300)


def test_unknown_openrouter_model_is_charged_at_the_dearest_by_output_price(qtbot, tmp_path):
    """Worst case is set mainly by output tokens, so the dearest model ranks by output price first."""
    input_heavy = ModelPrice("openrouter", "input/heavy", "Input heavy", 5.0, 1.0)
    output_heavy = ModelPrice("openrouter", "output/heavy", "Output heavy", 1.0, 9.0)
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=typed/model",))
    h = Harness(qtbot, tmp_path, FakeBackend(), config=config)
    h.service.set_live_prices("openrouter", (input_heavy, output_heavy))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert entry.cost == cost(output_heavy, 1200, 300)


def test_deepseek_cut_off_answer_is_not_retried(qtbot, tmp_path):
    """A cut-off answer comes back the same way with the same budget, so the retry is not sent."""
    backend = SequenceBackend(AiError("bad_response", "cut off", input_tokens=900, output_tokens=40, cut_off=True),
                              AiResult({"ok": True}, 1200, 300))
    h = Harness(qtbot, tmp_path, backend, config=Config(ai_enabled=True, ai_provider="deepseek"))
    with qtbot.waitSignal(h.service.failed):
        assert h.service.submit(request()) is True
    assert len(backend.calls) == 1
    assert h.kinds == ["bad_response"]
    assert len(read_entries(h.ledger)) == 1


def test_openrouter_reported_cost_far_above_the_list_price_is_ignored(qtbot, tmp_path, caplog):
    """More than 10x the worst case at list price: the list-price cost is recorded and the key is not logged."""
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=1.0))
    h = Harness(qtbot, tmp_path, backend, config=config, key="sk-or-secret")
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with caplog.at_level("WARNING", logger="proofline.ai_service"), qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert (entry.cost, entry.cost_known) == (cost(OPENROUTER_CHEAP, 1200, 300), True)
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("list price" in message for message in warnings)
    assert all("sk-or-secret" not in r.getMessage() and "cheap/model" not in r.getMessage()
               for r in caplog.records)


def test_openrouter_reported_cost_within_ten_times_the_worst_case_is_kept(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    # The worst case for request() at list price is about 0.00022 dollars, so 0.002 is under 10x of it.
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=0.002))
    h = Harness(qtbot, tmp_path, backend, config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert (entry.cost, entry.cost_known) == (0.002, True)


def test_openrouter_reported_cost_just_over_ten_times_the_worst_case_is_ignored(qtbot, tmp_path):
    config = Config(ai_enabled=True, ai_provider="openrouter", ai_models=("openrouter=cheap/model",))
    worst = cost(OPENROUTER_CHEAP, estimate_input_tokens(request().text), 2000)
    backend = FakeBackend(result=AiResult({"ok": True}, 1200, 300, cost=worst * 10 + 0.0001))
    h = Harness(qtbot, tmp_path, backend, config=config)
    h.service.set_live_prices("openrouter", (OPENROUTER_CHEAP,))
    with qtbot.waitSignal(h.service.finished):
        assert h.service.submit(request()) is True
    [entry] = read_entries(h.ledger)
    assert entry.cost == cost(OPENROUTER_CHEAP, 1200, 300)
